"""任务状态侧边栏 —— 展示当前任务（state 文件）和计划任务（task_{ts}.json）"""

import sys
import json, os, subprocess, platform
from datetime import datetime
import flet as ft
from task_attribute_manager import TaskAttributeManager
from task_manager import TaskManager, SubTaskStatus


class StatusSidebar:
    """左侧任务状态面板"""

    WIDTH: int = 260
    BGCOLOR = ft.Colors.GREY_50
    TITLE_BGCOLOR = ft.Colors.GREY_100
    DIALOG_BGCOLOR = ft.Colors.WHITE
    EMPTY_TEXT: str = "暂无任务"

    STATUS_COLORS = {
        SubTaskStatus.COMPLETED.value: ft.Colors.GREEN,
        SubTaskStatus.IN_PROGRESS.value: ft.Colors.BLUE,
        SubTaskStatus.FAILED.value: ft.Colors.RED,
        SubTaskStatus.PENDING.value: ft.Colors.ORANGE,
        SubTaskStatus.SKIPPED.value: ft.Colors.TEAL,

    }
    STATUS_LABELS = {
        SubTaskStatus.COMPLETED.value: "已完成",
        SubTaskStatus.IN_PROGRESS.value: "进行中",
        SubTaskStatus.FAILED.value: "失败",
        SubTaskStatus.PENDING.value: "待执行",
        SubTaskStatus.SKIPPED.value: "跳过",

    }

    def __init__(self, page: ft.Page, task_dir: str, token_file: str = "", visible: bool = True, extra_controls: list = None, on_chat_select=None, config=None, eqm=None):
        self.page = page
        self._eqm = eqm
        self.task_dir = task_dir
        self.token_file = token_file
        self._config = config
        self.task_config_file_path = os.path.join(self.task_dir, "task_config.json")
        self._visible = visible
        self._extra_controls = extra_controls or []
        self._on_chat_select = on_chat_select
        self._selected_task_file = ""
        self._ds = {}
        self._needs_refresh = False
        self._last_data_hash = None
        self._build()

    @property
    def container(self) -> ft.Container:
        return self._panel

    @property
    def visible(self) -> bool:
        return self._panel.visible

    def toggle(self):
        self._panel.visible = not self._panel.visible
        self.refresh()
        self.page.update()

    def refresh(self):
        tasks, pending, skipped = self._load_all()

        # hash 缓存：数据不变且无强制刷新标记时跳过重建
        import hashlib, json as _json
        data_str = _json.dumps({"tasks": tasks, "pending": pending, "skipped": skipped, "selected": self._selected_task_file}, sort_keys=True, default=str)
        data_hash = hashlib.md5(data_str.encode()).hexdigest()
        if not self._needs_refresh and data_hash == self._last_data_hash:
            return
        self._last_data_hash = data_hash
        self._needs_refresh = False

        self._history_list.controls.clear()

        for t in skipped + tasks + pending:
            self._history_list.controls.append(self._task_card(t))

        # 全空时提示
        if not tasks and not pending and not skipped:
            self._history_list.controls.append(
                ft.Text(self.EMPTY_TEXT, size=12, color=ft.Colors.GREY_400, italic=True))

        self.page.update()

    # ── 内部构建 ──

    def _build(self):
        self._history_list = ft.ListView(spacing=4, padding=ft.Padding(8, 4, 8, 4), expand=True)
        def _on_panel_click(e):
            if not self._selected_task_file:
                return
            self._selected_task_file = ""
            self._needs_refresh = True
            self.refresh()
            if self._config.execution.config_work_dir and self._on_chat_select:
                self._on_chat_select(self._config.execution.config_work_dir, "")

        content_col = ft.Column([
            ft.Container(content=self._build_title_bar(), expand=7),
            ft.Container(
                content=ft.Column([
                    ft.Container(content=self._history_list, expand=True),
                ], spacing=4, expand=True),
                expand=86,
            ),
            ft.Container(
                content=self._build_exit_bar(),
                expand=7,
            ),
        ], spacing=0, expand=True)
        self._panel = ft.Container(
            visible=self._visible,
            width=self.WIDTH,
            bgcolor=self.BGCOLOR,
            content=content_col,
            on_click=_on_panel_click,
        )

    def _build_title_bar(self) -> ft.Container:
        add_btn = ft.IconButton(
            icon=ft.Icons.ADD, icon_size=18, tooltip="添加任务",
            on_click=lambda e: self._show_add_task_dialog())
        title_row = [add_btn]
        if self._extra_controls:
            title_row.append(ft.Row(self._extra_controls, spacing=4))
        return ft.Container(
            content=ft.Row(title_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.Padding(12, 8, 12, 8),
            bgcolor=self.TITLE_BGCOLOR,
        )
    
    def _build_exit_bar(self) -> ft.Container:
        return ft.Container(
            content=ft.Row([
                ft.IconButton(
                    icon=ft.Icons.EXIT_TO_APP, icon_size=18,
                    icon_color=ft.Colors.GREY_400,
                    tooltip="退出", on_click=self._on_exit,
                ),
            ], expand=True),
            padding=ft.Padding(12, 8, 12, 8),
            expand=True,
            bgcolor=ft.Colors.WHITE,
        )

    def _on_exit(self, e):
        def do_exit(close_event):
            try:
                if self.token_file and os.path.exists(self.token_file):
                    os.remove(self.token_file)
            except Exception:
                pass
            self.page.run_task(self.page.window.destroy)
        dialog = ft.AlertDialog(
            bgcolor=self.DIALOG_BGCOLOR,
            shape=ft.RoundedRectangleBorder(radius=6),
            content_padding=ft.Padding(16, 16, 16, 16),
            title=ft.Text("确认退出"),
            content=ft.Text("确定要退出吗？"),
            actions=[ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                     ft.TextButton("退出", on_click=lambda e: [self.page.pop_dialog(), do_exit(e)])],
        )
        self.page.show_dialog(dialog)

    # ── 数据加载 ──

    def _load_all(self) -> tuple:
        """返回 (当前任务列表, 计划任务列表, 已跳过任务列表)"""
        all_tasks = TaskManager.list_history_tasks(self.task_dir)
        valid_tasks = []
        for t in all_tasks:
            pp = t.get("project_path", "")
            if pp and not os.path.isdir(pp):
                sf = t.get("file_full_path", "")
                if sf and os.path.isfile(sf):
                    os.remove(sf)
                continue
            valid_tasks.append(t)
        terminal = {"completed", "failed"}
        skip_status = SubTaskStatus.SKIPPED.value

        tasks = [t for t in valid_tasks
                 if t["status"] in terminal and not t.get("is_periodic", False)
                 and t["status"] != skip_status]
        pending = [t for t in valid_tasks
                   if t["status"] != skip_status and (
                       t.get("is_periodic", False) or t["status"] not in terminal)]
        skipped = [t for t in valid_tasks if t["status"] == skip_status]
        return tasks, pending, skipped

    # ── 卡片 ──

    def _status_badge(self, status: str) -> ft.Container:
        color = self.STATUS_COLORS.get(status, ft.Colors.GREY)
        label = self.STATUS_LABELS.get(status, status)
        return ft.Container(
            content=ft.Text(label, size=9, color=ft.Colors.WHITE),
            bgcolor=color, border_radius=2,
            padding=ft.Padding(3, 1, 3, 1),
        )

    def _task_card(self, task: dict) -> ft.Container:
        """任务卡片（单选）；周期任务额外显示图标、次数、下次执行时间"""
        name = (task.get("name") or task.get("task_name", "未知任务"))[:36]
        status = task.get("status", SubTaskStatus.PENDING.value)

        # SKIPPED 状态极简卡片：仅名称 + 编辑按钮
        if status == SubTaskStatus.SKIPPED.value:
            key = task.get("file_full_path") or task.get("file", "")
            selected = (self._selected_task_file == key)
            menu_items = [
                ft.PopupMenuItem(content=ft.Text("编辑", size=14),
                                 on_click=lambda e, t=task: self._show_add_task_dialog(task_data=t)),
                ft.PopupMenuItem(content=ft.Text("删除", size=14),
                                 on_click=lambda e, t=task: self._confirm_delete_task(
                                     t.get("file_full_path") or t.get("file", ""),
                                     t.get("name") or t.get("task_name", ""))),
            ]
            card = ft.Container(
                content=ft.Row([
                    ft.Text(name, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                            color=ft.Colors.BLACK87 if selected else ft.Colors.GREY_700),
                    ft.PopupMenuButton(icon=ft.icons.Icons.MORE_VERT, items=menu_items, icon_size=16, menu_position=ft.PopupMenuPosition.UNDER),
                ], height=32, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=ft.Colors.WHITE, border_radius=6,
                on_click=lambda e, k=key, p=task.get("project_path", ""),
                              s=key: self._select_card(k, p, s),
                padding=ft.Padding(8, 6, 8, 6),
                border=ft.border.Border(
                    left=ft.BorderSide(0, ft.Colors.TRANSPARENT),
                    top=ft.BorderSide(0, ft.Colors.TRANSPARENT),
                    right=ft.BorderSide(0, ft.Colors.TRANSPARENT),
                    bottom=ft.BorderSide(1, ft.Colors.GREY_200),
                ),
            )
            if selected:
                card.bgcolor = ft.Colors.BLUE_50
            return card

        pp = task.get("project_path", "")
        state_file = task.get("file_full_path") or task.get("file", "")
        key = state_file
        selected = (self._selected_task_file == key)
        is_pending = task.get("is_periodic", False) or task.get("status", "") in ("pending", "in_progress")
        is_periodic = task.get("is_periodic", False)
        periodic_counter = task.get("periodic_counter", 0)
        next_time = task.get("next_execution_time", "")
        next_display = ""
        if next_time:
            try:
                dt = datetime.fromisoformat(next_time)
                next_display = dt.strftime("%m/%d %H:%M")
            except Exception:
                next_display = next_time[:16]

        menu_items = [
            ft.PopupMenuItem(content=ft.Text("编辑", size=14),
                             on_click=lambda e, t=task: self._show_add_task_dialog(task_data=t)),
            ft.PopupMenuItem(content=ft.Text("删除", size=14),
                             on_click=lambda e, t=task: self._confirm_delete_task(
                                 t.get("file_full_path") or t.get("file", ""),
                                 t.get("name") or t.get("task_name", ""))),
        ]
        if is_pending:
            menu_items.append(
                ft.PopupMenuItem(content=ft.Text("启动", size=14),
                                 on_click=lambda e, f=state_file: self._start_pending(f)))

        name_children = []
        name_children.append(
            ft.Text(name, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                    color=ft.Colors.BLACK87 if selected else ft.Colors.GREY_700))

        if is_periodic or status == "pending":
            name_children.append(ft.Text(" | ", size=11, color=ft.Colors.GREY_400))
        if is_periodic:
            name_children.append(ft.Text("🔄", size=11))
        elif status == "pending":
            name_children.append(ft.Text("➡️", size=11))

        name_children.append(ft.Text(" | ", size=11, color=ft.Colors.GREY_400))
        name_children.append(self._status_badge(status))

        col_children = [
            ft.Row(name_children, spacing=0, expand=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]
        if is_periodic or (status == "pending" and next_display):
            extras = []
            if periodic_counter:
                extras.append(f"第{periodic_counter}次")
            if next_display:
                extras.append(f"下次: {next_display}")
            if extras:
                col_children.append(
                    ft.Text(" · ".join(extras), size=10, color=ft.Colors.GREY_500))

        card = ft.Container(
            content=ft.Row([
                ft.Column(col_children, expand=True, spacing=0),
                ft.PopupMenuButton(icon=ft.icons.Icons.MORE_VERT, 
                                   items=menu_items, icon_size=16, menu_position=ft.PopupMenuPosition.UNDER),
            ],height=32, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=ft.Colors.WHITE, border_radius=6,
            padding=ft.Padding(8, 6, 8, 6),
            border=ft.border.Border(
                left=ft.BorderSide(0, ft.Colors.TRANSPARENT),
                top=ft.BorderSide(0, ft.Colors.TRANSPARENT),
                right=ft.BorderSide(0, ft.Colors.TRANSPARENT),
                bottom=ft.BorderSide(1, ft.Colors.GREY_200),
            ),
            on_click=lambda e, k=key, p=pp, s=state_file: self._select_card(k, p, s),
        )
        if selected:
            card.bgcolor = ft.Colors.BLUE_50
        return card

    def _select_card(self, key: str, path: str, state_file: str = ""):
        """选中卡片，切换项目目录。"""
        if key == self._selected_task_file:
            # 点击已选中卡片：取消选中，重置回默认目录
            self._selected_task_file = ""
            self._needs_refresh = True
            self.refresh()
            if self._config.execution.config_work_dir and self._on_chat_select:
                self._on_chat_select(self._config.execution.config_work_dir, "")
            return
        self._selected_task_file = key
        if path and self._on_chat_select:
            self._on_chat_select(path, state_file)
        self._needs_refresh = True
        self.refresh()

    # ── 菜单操作 ──

    def _open_dialog(self, dlg):
        self.page.show_dialog(dlg)

    def _close_dialog(self, dlg):
        dlg.open = False
        dlg.update()
    

    def _remove_overlay(self, control):
        try:
            self.page.overlay.remove(control)
            self.page.update()
        except (ValueError, AssertionError):
            pass

    def _pick_folder(self, field):
        """选择文件夹，结果写入 field.value"""
        import subprocess as _sp
        if self._config.system == "windows":
            try:
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$o=New-Object System.Windows.Forms.Form; "
                    "$o.TopMost=$true; $o.ShowInTaskbar=$false; "
                    "$o.WindowState='Minimized'; $o.Show(); "
                    "$d=New-Object System.Windows.Forms.FolderBrowserDialog; "
                    "$d.Description='选择项目文件夹'; "
                    "$r=($d.ShowDialog($o) -eq 'OK'); "
                    "$o.Close(); "
                    "if($r){$d.SelectedPath}"
                )
                r = _sp.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
                )
                path = r.stdout.strip()
                if path:
                    field.value = path
                    field.update()
            except Exception as e:
                if self._eqm:
                    self._eqm.send_display(f"[WARN] 选择文件夹失败: {e}", style="task")
                else:
                    import sys
                    print(f"[WARN] 选择文件夹失败: {e}", file=sys.stderr)
        else:
            if self._config.system == "darwin":
                try:
                    r = _sp.run(
                        ["osascript", "-e", 'POSIX path of (choose folder with prompt "选择文件夹")'],
                        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
                    )
                    path = r.stdout.strip()
                    if path:
                        field.value = path
                        field.update()
                except Exception as e:
                    if self._eqm:
                        self._eqm.send_display(f"[WARN] 选择文件夹失败: {e}", style="task")
                    else:
                        import sys
                        print(f"[WARN] 选择文件夹失败: {e}", file=sys.stderr)
            else:
                try:
                    r = _sp.run(
                        ["zenity", "--file-selection", "--directory", "--title=选择文件夹"],
                        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
                    )
                    path = r.stdout.strip()
                    if path:
                        field.value = path
                        field.update()
                except Exception as e:
                    if self._eqm:
                        self._eqm.send_display(f"[WARN] zenity 选择文件夹失败: {e}", style="task")
                    else:
                        import sys
                        print(f"[WARN] zenity 选择文件夹失败: {e}", file=sys.stderr)

    def _save_new_task(self, data: dict):
        """创建新任务文件并保存"""
        from task_manager import SubTaskRecord
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_name = f"task_{ts}_state.json"
        file_path = os.path.join(self.task_dir, file_name)

        task_name = data.get("task_name", "").strip()
        sub_detail = data.get("sub_task_detail", "").strip()
        rec = SubTaskRecord(
            index=0,
            sub_task_name=task_name or (sub_detail[:30] if sub_detail else "新任务"),
            sub_task_detail=sub_detail,
            task_type=data.get("task_type", ""),
            task_sub_type=data.get("task_sub_type", ""),
            next_execution_time=data.get("next_execution_time", ""),
            is_periodic=data.get("is_periodic", False),
            period=data.get("period", "1d") if data.get("is_periodic") else "",
            is_interactive=data.get("is_interactive", False),
            project_path=data.get("project_path", ""),
            extra_prompt=data.get("extra_prompt", ""),
            status=SubTaskStatus(data.get("status", SubTaskStatus.PENDING.value)),
        )

        tm = TaskManager(save_path=file_path)
        tm._subtask = rec
        tm.save(file_path)
        self.refresh()

    def _show_add_task_dialog(self, task_data=None):
        """统一任务对话框：task_data=None 新建，否则编辑"""
        attr_mgr = TaskAttributeManager(json_path=self.task_config_file_path)
        categories = attr_mgr.get_categories()
        cat_names = list(categories.keys())
        is_edit = task_data is not None

        if is_edit:
            state_file = task_data.get("file_full_path") or task_data.get("file", "")
            if state_file and os.path.exists(state_file):
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        sd = json.load(f)
                    sub = sd.get("subtask", {})
                    pd = sd.get("periodic", {})
                    _name = sub.get("sub_task_name", task_data.get("name", task_data.get("task_name", "")))
                    _detail = sub.get("sub_task_detail", "")
                    _time = pd.get("next_execution_time", sub.get("next_execution_time", ""))
                    _path = sub.get("project_path", task_data.get("project_path", ""))
                    _periodic = pd.get("is_periodic", sub.get("is_periodic", False))
                    _period = pd.get("period", sub.get("period", "1d"))
                    _interactive = sub.get("is_interactive", False)
                    _status = sub.get("status", SubTaskStatus.PENDING.value)
                    _cat = sub.get("task_type", "")
                    _sub_cat = sub.get("task_sub_type", "")
                except Exception:
                    _name = task_data.get("name", task_data.get("task_name", ""))
                    _detail = _time = _path = _cat = _sub_cat = ""
                    _periodic = _interactive = False
                    _period = "1d"
                    _status = task_data.get("status", SubTaskStatus.PENDING.value)
            else:
                _name = task_data.get("task_name", "")
                _detail = _time = _path = _cat = _sub_cat = ""
                _periodic = _interactive = False
                _period = "1d"
                _status = task_data.get("status", SubTaskStatus.PENDING.value)
            current_cat = _cat or (cat_names[0] if cat_names else "")
        else:
            if not cat_names:
                return
            _name = _detail = _time = _sub_cat = ""
            _path = self._config.paths.current_work_dir
            _periodic = _interactive = False
            _period = "1d"
            _status = SubTaskStatus.SKIPPED.value
            current_cat = cat_names[0]

        current_subs = [s[0] for s in categories.get(current_cat, [])]

        cat_dd = ft.Dropdown(
            options=[ft.dropdown.Option(key=n, text=n) for n in cat_names],
            value=current_cat, dense=True, expand=True,
        )
        sub_dd = ft.Dropdown(
            options=[ft.dropdown.Option(key=n, text=n) for n in current_subs],
            value=_sub_cat if is_edit and _sub_cat else (current_subs[0] if current_subs else ""),
            dense=True, expand=True,
        )
        path_field = ft.TextField(
                    label="项目路径", hint_text="选择项目文件夹（必填）",
                    value=_path, dense=True, read_only=True,
                    border_color=ft.Colors.GREY_300, prefix_icon=ft.Icons.FOLDER_OPEN, expand=True,
                )
        name_field = ft.TextField(
            label="任务名称", hint_text="输入任务名称",
            value=_name, border_color=ft.Colors.GREY_300, dense=True, expand=True,
        )
        detail_field = ft.TextField(
            label="任务描述", hint_text="简要描述任务内容",
            value=_detail, border_color=ft.Colors.GREY_300,
            prefix_icon=ft.Icons.TASK_ALT, multiline=True,
            expand=True, min_lines=2, max_lines=4, dense=True,
        )

        time_data = {"value": _time}
        time_display = ft.Text(
            _time or "点击选择执行时间", size=13,
            color=ft.Colors.GREY_700 if _time else ft.Colors.GREY_400,
            italic=not bool(_time), expand=True,
        )
        picker_ref = ft.Ref[ft.CupertinoDatePicker]()
        pick_btn = ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH, tooltip="选择执行时间", icon_size=18,
        )

        
        path_btn = ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="选择文件夹", icon_size=18)
        path_error = ft.Text("", size=11, color=ft.Colors.RED_400, visible=False)

        gs = ft.BorderSide(1, ft.Colors.GREY_300)

        periodic_switch = ft.Switch(label="周期任务", value=_periodic)
        period_field = ft.TextField(
            label="周期间隔", hint_text="如 1d / 12h / 30m",
            value=_period, dense=True, visible=_periodic,
        )
        interactive_switch = ft.Switch(label="交互模式", value=_interactive)
        status_dd = ft.Dropdown(
            label="任务状态",
            options=[ft.dropdown.Option(key=SubTaskStatus.SKIPPED.value, text="已跳过"),
                     ft.dropdown.Option(key=SubTaskStatus.PENDING.value, text="待处理"),
                     ft.dropdown.Option(key=SubTaskStatus.IN_PROGRESS.value, text="执行中"),
                     ft.dropdown.Option(key=SubTaskStatus.COMPLETED.value, text="已完成"),
                     ft.dropdown.Option(key=SubTaskStatus.FAILED.value, text="已失败")
                     ],
            value=_status, dense=True, expand=True,
        )

        self._ds = {
            "is_edit": is_edit, "task_data": task_data,
            "categories": categories,
            "cat_dd": cat_dd, "sub_dd": sub_dd,
            "name_field": name_field, "detail_field": detail_field,
            "time_data": time_data, "time_display": time_display,
            "picker_ref": picker_ref, "time_dialog": None,
            "path_field": path_field, "path_error": path_error,
            "periodic_switch": periodic_switch,
            "period_field": period_field,
            "interactive_switch": interactive_switch,
            "status_dd": status_dd,
            "form": {
                "task_type": current_cat,
                "task_sub_type": sub_dd.value,
                "task_name": _name, "sub_task_detail": _detail,
                "next_execution_time": _time, "project_path": _path,
                "is_periodic": _periodic, "period": _period,
                "is_interactive": _interactive, "status": _status,
            },
        }

        cat_dd.on_select = self._on_dlg_cat_change
        sub_dd.on_select = self._on_dlg_sub_change
        pick_btn.on_click = self._on_dlg_pick_time
        path_btn.on_click = self._on_dlg_pick_path
        periodic_switch.on_change = self._on_dlg_periodic_change

        content_sections = []

        if not is_edit:
            content_sections.append(ft.Column([
                ft.Text("任务类型", size=12, color=ft.Colors.GREY_500,
                        weight=ft.FontWeight.BOLD),
                ft.Row([cat_dd, sub_dd], spacing=8),
            ], spacing=6))

        if not is_edit:
            content_sections.append(ft.Column([
                ft.Text("项目路径", size=12, color=ft.Colors.GREY_500,
                        weight=ft.FontWeight.BOLD),
                ft.Row([path_field, path_btn], spacing=4),
                path_error,
            ], spacing=6))

        content_sections.append(ft.Column([
            ft.Text("任务描述", size=12, color=ft.Colors.GREY_500,
                    weight=ft.FontWeight.BOLD),
            name_field, detail_field,
        ], spacing=10))

        content_sections.append(ft.Column([
            ft.Text("执行时间", size=12, color=ft.Colors.GREY_500,
                    weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Row([time_display, pick_btn], spacing=8,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                border=ft.Border(top=gs, left=gs, right=gs, bottom=gs),
                border_radius=1,
                padding=ft.Padding(left=8, top=0, right=8, bottom=0),
            ),
        ], spacing=6))

        content_sections.append(ft.Column([
            ft.Text("任务设置", size=12, color=ft.Colors.GREY_500,
                    weight=ft.FontWeight.BOLD),
            periodic_switch, period_field, interactive_switch, status_dd,
        ], spacing=10))

        title_text = "编辑任务" if is_edit else "添加任务"
        title_icon = ft.Icons.EDIT_NOTE if is_edit else ft.Icons.ADD_TASK

        dlg = ft.AlertDialog(
            bgcolor=self.DIALOG_BGCOLOR,
            shape=ft.RoundedRectangleBorder(radius=6),
            content_padding=ft.Padding(16, 16, 16, 16),
            actions_padding=ft.Padding(20, 0, 20, 10),
            title=ft.Row([
                ft.Icon(title_icon, size=20),
                ft.Text(title_text, size=16, weight=ft.FontWeight.BOLD),
            ]),
            content=ft.Column(
                content_sections,
                spacing=16, width=400, tight=True, scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.FilledButton("保存", on_click=self._on_dlg_save),
            ],
        )
        self._ds["dlg"] = dlg
        self._open_dialog(dlg)

    # ── 扁平化事件处理 ──

    def _on_dlg_cat_change(self, e):
        ds = self._ds
        ds["form"]["task_type"] = ds["cat_dd"].value or ""
        new_subs = [s[0] for s in ds["categories"].get(ds["form"]["task_type"], [])]
        ds["sub_dd"].options = [ft.dropdown.Option(key=n, text=n) for n in new_subs]
        if new_subs:
            ds["sub_dd"].value = new_subs[0]
            ds["form"]["task_sub_type"] = new_subs[0]
        else:
            ds["sub_dd"].value = None
            ds["form"]["task_sub_type"] = ""
        ds["dlg"].update()

    def _on_dlg_sub_change(self, e):
        self._ds["form"]["task_sub_type"] = self._ds["sub_dd"].value or ""

    def _on_dlg_pick_time(self, e):
        ds = self._ds
        td = ft.AlertDialog(
            bgcolor=self.DIALOG_BGCOLOR,
            shape=ft.RoundedRectangleBorder(radius=6),
            content_padding=ft.Padding(16, 16, 16, 16),
            title=ft.Text("选择执行时间"),
            content=ft.Container(
                content=ft.CupertinoDatePicker(
                    ref=ds["picker_ref"],
                    value=datetime.now(),
                    use_24h_format=True,
                    date_picker_mode=ft.CupertinoDatePickerMode.DATE_AND_TIME,
                    minute_interval=1,
                ),
                height=220,
            ),
            actions=[ft.TextButton("确定", on_click=self._on_dlg_confirm_time)],
        )
        ds["time_dialog"] = td
        self.page.show_dialog(td)

    def _on_dlg_confirm_time(self, e):
        ds = self._ds
        p = ds["picker_ref"].current
        if p and p.value:
            v = p.value.strftime("%Y-%m-%d %H:%M:%S")
            ds["time_data"]["value"] = v
            ds["form"]["next_execution_time"] = v
            ds["time_display"].value = v
            ds["time_display"].color = ft.Colors.GREY_700
            ds["time_display"].italic = False
            ds["time_display"].update()
        if ds["time_dialog"]:
            ds["time_dialog"].open = False
        self.page.update()

    def _on_dlg_pick_path(self, e):
        """选择文件夹"""
        self._pick_folder(self._ds["path_field"])

    def _on_dlg_periodic_change(self, e):
        ds = self._ds
        v = e.control.value
        ds["form"]["is_periodic"] = v
        ds["period_field"].visible = v
        ds["period_field"].update()
        self.page.update()

    def _on_dlg_save(self, e):
        ds = self._ds
        if not ds:
            return
        is_edit = ds.get("is_edit", False)

        if not is_edit and not ds["path_field"].value:
            ds["path_error"].value = "请选择项目路径"
            ds["path_error"].visible = True
            ds["dlg"].update()
            return

        ds["form"]["task_name"] = ds["name_field"].value or ""
        ds["form"]["sub_task_detail"] = ds["detail_field"].value or ""
        ds["form"]["next_execution_time"] = ds["time_data"]["value"]
        ds["form"]["project_path"] = ds["path_field"].value or ""
        ds["form"]["period"] = ds["period_field"].value or "1d"
        ds["form"]["status"] = ds["status_dd"].value
        ds["form"]["is_interactive"] = ds["interactive_switch"].value

        self._close_dialog(ds["dlg"])

        if is_edit:
            self._save_edit(ds["task_data"], ds["form"])
        else:
            self._save_new_task(ds["form"])

        self._ds = {}

    def _save_edit(self, task_data: dict, form: dict):
        """编辑保存 — TaskManager 统一路径"""
        state_file = task_data.get("file_full_path") or task_data.get("file", "")
        if not state_file or not os.path.exists(state_file):
            return
        try:
            tm = TaskManager.load(state_file)
            if tm._subtask:
                tm._subtask.sub_task_name = form.get("task_name", "")
                tm._subtask.sub_task_detail = form.get("sub_task_detail", "")
                tm._subtask.next_execution_time = form.get("next_execution_time", "")
                tm._subtask.is_periodic = form.get("is_periodic", False)
                tm._subtask.period = form.get("period", "")
                tm._subtask.is_interactive = form.get("is_interactive", False)
                tm._subtask.status = SubTaskStatus(form.get("status", "pending"))
                tm.save(state_file)
        except Exception:
            pass
        self.refresh()

    # ── 删除 ──

    def _confirm_delete_task(self, state_file: str, name: str):
        """确认删除任务／计划"""

        def _do_delete(e):
            self._close_dialog(dlg)
            if state_file and os.path.exists(state_file):
                os.remove(state_file)
            self._selected_task_file = ""
            self.refresh()

        dlg = ft.AlertDialog(
            bgcolor=self.DIALOG_BGCOLOR,
            shape=ft.RoundedRectangleBorder(radius=6),
            content_padding=ft.Padding(16, 16, 16, 16),
            title=ft.Text("确认删除"),
            content=ft.Text(f"确认删除任务「{name}」？此操作不可撤销。", size=13),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.FilledButton("确认删除", on_click=_do_delete),
            ],
        )
        self._open_dialog(dlg)

    # ── 计划任务操作 ──

    def _start_pending(self, file_path: str):
        """立即启动计划任务：将执行时间设为现在"""
        if not file_path or not os.path.exists(file_path):
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 更新 periodic 层（list_history_tasks 优先读取）
            if "periodic" in data:
                data["periodic"]["next_execution_time"] = now
            # 更新 subtask 层（兜底读取）
            if "subtask" in data:
                data["subtask"]["next_execution_time"] = now
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            return
        self.refresh()

    def _open_project(self, task: dict):
        """在文件管理器中打开项目路径"""
        pp = task.get("project_path", "")
        if not pp:
            return
        try:
            if self._config.system == "windows":
                os.startfile(pp)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", pp])
            else:
                subprocess.Popen(["xdg-open", pp])
        except Exception:
            pass

