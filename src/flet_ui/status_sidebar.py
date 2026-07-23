"""任务状态侧边栏 —— 展示当前任务（state 文件）和计划任务（task_{ts}.json）"""

import json, os, subprocess, platform
from datetime import datetime
import flet as ft
from task_attribute_manager import TaskAttributeManager
from task_manager import TaskManager, SubTaskStatus


class StatusSidebar:
    """左侧任务状态面板"""

    WIDTH: int = 260
    BGCOLOR = ft.Colors.GREY_50
    TITLE_BGCOLOR = ft.Colors.BLUE_GREY_50
    DIALOG_BGCOLOR = ft.Colors.WHITE
    TITLE: str = "任务状态"
    EMPTY_TEXT: str = "暂无任务"

    STATUS_COLORS = {
        SubTaskStatus.COMPLETED.value: ft.Colors.GREEN,
        SubTaskStatus.IN_PROGRESS.value: ft.Colors.BLUE,
        SubTaskStatus.FAILED.value: ft.Colors.RED,
        SubTaskStatus.PENDING.value: ft.Colors.ORANGE,
    }
    STATUS_LABELS = {
        SubTaskStatus.COMPLETED.value: "已完成",
        SubTaskStatus.IN_PROGRESS.value: "进行中",
        SubTaskStatus.FAILED.value: "失败",
        SubTaskStatus.PENDING.value: "待执行",
    }

    def __init__(self, page: ft.Page, task_dir: str, visible: bool = True, extra_controls: list = None, on_chat_select=None):
        self.page = page
        self.task_dir = task_dir
        self.task_config_file_path = os.path.join(self.task_dir, "task_config.json")
        self._visible = visible
        self._extra_controls = extra_controls or []
        self._on_chat_select = on_chat_select
        self._default_work_dir = ""
        self._selected_key = ""
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
        tasks, pending, chat_tasks = self._load_all()

        # hash 缓存：数据不变且无强制刷新标记时跳过重建
        import hashlib, json as _json
        data_str = _json.dumps({"tasks": tasks, "pending": pending, "selected_key": self._selected_key}, sort_keys=True, default=str)
        data_hash = hashlib.md5(data_str.encode()).hexdigest()
        if not self._needs_refresh and data_hash == self._last_data_hash:
            return
        self._last_data_hash = data_hash
        self._needs_refresh = False

        self._history_list.controls.clear()
        self._pending_list.controls.clear()

        # 历史任务
        if tasks:
            for t in tasks:
                self._history_list.controls.append(self._task_card(t))
        else:
            self._history_list.controls.append(
                ft.Text(self.EMPTY_TEXT, size=12, color=ft.Colors.GREY_400, italic=True))

        # 计划任务
        if pending:
            for idx, p in enumerate(pending):
                self._pending_list.controls.append(self._pending_card(p, idx))
        else:
            self._pending_list.controls.append(
                ft.Text(self.EMPTY_TEXT, size=12, color=ft.Colors.GREY_400, italic=True))

        self.page.update()

    # ── 内部构建 ──

    def _build(self):
        self._history_list = ft.ListView(spacing=4, padding=ft.Padding(8, 4, 8, 4), expand=True)
        self._pending_list = ft.ListView(spacing=4, padding=ft.Padding(8, 4, 8, 4), expand=True)

        def _on_panel_click(e):
            if not self._selected_key:
                return
            self._selected_key = ""
            self._needs_refresh = True
            self.refresh()
            if self._default_work_dir and self._on_chat_select:
                self._on_chat_select(self._default_work_dir, "")

        content_col = ft.Column([
            ft.Container(content=self._build_title_bar(), expand=1),
            ft.Container(
                content=ft.Column([
                    ft.Text(" 任务", size=11, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_500),
                    ft.Container(content=self._history_list, expand=True),
                ], spacing=4, expand=True),
                expand=5,
            ),
            ft.Container(
                content=ft.Column([
                    ft.Text(" 计划", size=11, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_500),
                    ft.Container(content=self._pending_list, expand=True),
                ], spacing=4, expand=True),
                expand=3,
            ),
            ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.EXIT_TO_APP,
                    icon_color=ft.Colors.GREY_400,
                    tooltip="退出",
                    expand=True
                ),
                padding=ft.Padding(12, 8, 12, 8),
                bgcolor=ft.Colors.WHITE,
                expand=1,
            ),
        ], spacing=0, expand=True)
        self._panel = ft.Container(
            visible=self._visible,
            expand_loose=True,
            width=self.WIDTH,
            bgcolor=self.BGCOLOR,
            content=content_col,
            on_click=_on_panel_click,
        )

    def _build_title_bar(self) -> ft.Container:
        title_row = [] #[ft.Text(self.TITLE, weight=ft.FontWeight.W_600, size=13)]
        add_btn = ft.IconButton(
            icon=ft.Icons.ADD, icon_size=18, tooltip="添加任务",
            on_click=lambda e: self._show_add_task_dialog())
        title_row.append(add_btn)
        if self._extra_controls:
            title_row.append(ft.Row(self._extra_controls, spacing=4))
        return ft.Container(
            content=ft.Row(title_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.Padding(12, 8, 12, 8),
            bgcolor=self.TITLE_BGCOLOR,
        )

    # ── 数据加载 ──

    def _load_all(self) -> tuple:
        """返回 (当前任务列表, 计划任务列表)"""
        tasks = TaskManager.list_history_tasks(self.task_dir)
        pending = TaskManager.list_pending_tasks(self.task_dir)
        return tasks, pending, []

    # ── 卡片 ──

    def _card_border(self, color=ft.Colors.GREY_200) -> ft.border.Border:
        return ft.border.Border(
            left=ft.BorderSide(1, color),
            top=ft.BorderSide(1, color),
            right=ft.BorderSide(1, color),
            bottom=ft.BorderSide(1, color),
        )

    def _status_badge(self, status: str) -> ft.Container:
        color = self.STATUS_COLORS.get(status, ft.Colors.GREY)
        label = self.STATUS_LABELS.get(status, status)
        return ft.Container(
            content=ft.Text(label, size=9, color=ft.Colors.WHITE),
            bgcolor=color, border_radius=2,
            padding=ft.Padding(3, 1, 3, 1),
        )

    def _task_card(self, task: dict) -> ft.Container:
        """子任务卡片（扁平列表，单选）"""
        name = task.get("name", "未知任务")[:36]
        status = task.get("status", SubTaskStatus.PENDING.value)
        pp = task.get("project_path", "")
        state_file = task.get("state_file", "")
        key = state_file
        selected = (self._selected_key == key)
        menu_items = [
            ft.PopupMenuItem(content=ft.Text("删除", size=14),
                             on_click=lambda e, t=task: self._confirm_delete_task(t)),
        ]
        card = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Row([
                        ft.Text(name, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True,
                                color=ft.Colors.BLACK87 if selected else ft.Colors.GREY_700),
                        self._status_badge(status),
                    ], spacing=0, expand=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], expand=True),
                ft.PopupMenuButton(items=menu_items, icon_size=16),
            ],height=32, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=ft.Colors.WHITE, border_radius=6,
            padding=ft.Padding(8, 6, 4, 6),
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
        if key == self._selected_key:
            # 点击已选中卡片：取消选中，重置回默认目录
            self._selected_key = ""
            self._needs_refresh = True
            self.refresh()
            if self._default_work_dir and self._on_chat_select:
                self._on_chat_select(self._default_work_dir, "")
            return
        self._selected_key = key
        if path and self._on_chat_select:
            self._on_chat_select(path, state_file)
        self._needs_refresh = True
        self.refresh()

    def _pending_card(self, pending: dict, idx: int) -> ft.Container:
        name = pending.get("task_name", "未知")[:36]
        if len(pending.get("task_name", "")) > 36:
            name += "…"
        exec_time = pending.get("next_execution_time", "")
        periodic = " 🔁" if pending.get("is_periodic") else "➡️"
        status = pending.get("status", SubTaskStatus.PENDING.value)

        header = ft.Row([
            ft.Column([
                ft.Text(name + periodic, size=12, weight=ft.FontWeight.W_500,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(f"执行: {exec_time.replace('T', ' ').split('+')[0]}", size=10, color=ft.Colors.GREY_500, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1),
            ], expand=True, spacing=2),
            ft.Column([
                self._status_badge(status),
            ], tight=True),
        ], spacing=4)

        return ft.Container(
            content=ft.Column([header], spacing=4),
            bgcolor=ft.Colors.WHITE, border_radius=6,
            padding=ft.Padding(8, 6, 8, 6),
            border=self._card_border(),
            on_click=lambda e, p=pending, i=idx: self._on_pending_card_click(p, i),
        )

    # ── 菜单操作 ──

    def _open_dialog(self, dlg):
        self.page.show_dialog(dlg)

    def _close_dialog(self, dlg):
        dlg.open = False
        dlg.update()
    
    def _pick_folder(self, field):
        """zenity 选择文件夹，结果写入 field.value"""
        import subprocess
        try:
            r = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title=选择文件夹"],
                capture_output=True, text=True, timeout=30,
            )
            path = r.stdout.strip()
            if path:
                field.value = path
                field.update()
        except Exception:
            pass

    def _remove_overlay(self, control):
        try:
            self.page.overlay.remove(control)
            self.page.update()
        except (ValueError, AssertionError):
            pass

    def _show_pending_menu(self, pending: dict, idx: int):
        dlg = ft.AlertDialog(
            bgcolor=self.DIALOG_BGCOLOR,
            shape=ft.RoundedRectangleBorder(radius=3),
            content_padding=ft.Padding(20, 20, 20, 20),
            title=ft.Text("操作"),
            content=ft.Column([
                ft.TextButton("删除任务", on_click=lambda e: self._confirm_delete_pending_and_close(pending, dlg)),
            ], spacing=10),
        )
        self._open_dialog(dlg)

    def _open_project_and_close(self, task: dict, dlg: ft.AlertDialog):
        self._open_project(task)
        self._close_dialog(dlg)

    def _confirm_delete_and_close(self, task: dict, dlg: ft.AlertDialog):
        self._close_dialog(dlg)
        self._confirm_delete_task(task)

    def _confirm_delete_pending_and_close(self, pending: dict, dlg: ft.AlertDialog):
        self._close_dialog(dlg)
        self._confirm_delete_pending(pending)

    def _open_project(self, task: dict):
        """在系统文件管理器中打开项目文件夹"""
        path = task.get("project_path", "")
        if not path or not os.path.isdir(path):
            return
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", path])
        elif system == "Windows":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    def _open_path(self, path: str):
        """在系统文件管理器中打开指定路径"""
        if not path or not os.path.isdir(path):
            return
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", path])
        elif system == "Windows":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    def _confirm_delete_task(self, task: dict):
        """弹出确认对话框后删除历史任务记录"""
        def on_yes(e):
            self._close_dialog(dlg)
            self._delete_task(task)
        def on_no(e):
            self._close_dialog(dlg)

        name = task.get("name", "未知")[:30]
        dlg = ft.AlertDialog(
            bgcolor=self.DIALOG_BGCOLOR,
            shape=ft.RoundedRectangleBorder(radius=3),
            content_padding=ft.Padding(20, 20, 20, 20),
            title=ft.Text("确认删除"),
            content=ft.Text(f"确定删除项目「{name}」的记录吗？\n\n项目文件会一起删除。"),
            actions=[
                ft.TextButton("取消", on_click=on_no),
                ft.TextButton("删除", on_click=on_yes),
            ],
        )
        self._open_dialog(dlg)

    def _delete_task(self, task: dict):
        state_file = task.get("state_file")
        if state_file and os.path.exists(state_file):
            os.remove(state_file)
        self.refresh()

    def _on_pending_card_click(self, pending: dict, idx: int):
        try:
            self._show_pending_edit_dialog(pending, idx)
        except Exception as ex:
            import traceback
            traceback.print_exc()

    def _confirm_delete_pending(self, pending: dict):
        """弹出确认对话框后删除计划任务文件"""
        def on_yes(e):
            self._close_dialog(dlg)
            self._delete_pending(pending)

        def on_no(e):
            self._close_dialog(dlg)

        name = pending.get("task_name", "未知")[:30]
        dlg = ft.AlertDialog(
            bgcolor=self.DIALOG_BGCOLOR,
            shape=ft.RoundedRectangleBorder(radius=3),
            content_padding=ft.Padding(20, 20, 20, 20),
            title=ft.Text("确认删除"),
            content=ft.Text(f"确定删除计划任务「{name}」吗？"),
            actions=[
                ft.TextButton("取消", on_click=on_no),
                ft.TextButton("删除", on_click=on_yes),
            ],
        )
        self._open_dialog(dlg)

    def _delete_pending(self, pending: dict):
        file_path = pending.get("file", "")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        self.refresh()

    def _save_pending(self, pending: dict, updated: dict):
        """保存编辑后的计划任务，委托给 TaskManager.update_pending_task()"""
        file_path = pending.get("file", "")
        TaskManager.update_pending_task(file_path, {
            "task_name": updated.get("task_name", ""),
            "next_execution_time": updated.get("next_execution_time", ""),
            "is_periodic": updated.get("is_periodic", False),
            "period": updated.get("period", ""),
            "is_interactive": updated.get("is_interactive", False),
        })
        self.refresh()

    def _show_pending_edit_dialog(self, pending: dict, idx: int):
        """点击计划任务卡片时弹出编辑对话框"""
        # 时间可变状态
        time_data = {"value": pending.get("next_execution_time", "")}

        time_display = ft.Text(
            time_data["value"] or "点击选择执行时间",
            size=13,
            color=ft.Colors.GREY_700 if time_data["value"] else ft.Colors.GREY_400,
            italic=not bool(time_data["value"]),
            expand=True,
        )

        picker_ref = ft.Ref[ft.CupertinoDatePicker]()
        dialog = None

        def confirm_datetime(_):
            nonlocal dialog
            p = picker_ref.current
            if p and p.value:
                time_data["value"] = p.value.strftime("%Y-%m-%d %H:%M:%S")
                time_display.value = time_data["value"]
                time_display.color = ft.Colors.GREY_700
                time_display.italic = False
                time_display.update()
            if dialog:
                dialog.open = False
            self.page.update()

        def pick_datetime(_):
            nonlocal dialog
            dialog = ft.AlertDialog(
                title=ft.Text("选择执行时间"),
                content=ft.Container(
                    content=ft.CupertinoDatePicker(
                        ref=picker_ref,
                        value=datetime.now(),
                        use_24h_format=True,
                        date_picker_mode=ft.CupertinoDatePickerMode.DATE_AND_TIME,
                        minute_interval=1,
                    ),
                    height=220,
                ),
                actions=[ft.TextButton("确定", on_click=confirm_datetime)],
            )
            self.page.show_dialog(dialog)

        pick_btn = ft.IconButton(
            icon=ft.icons.Icons.CALENDAR_MONTH,
            tooltip="选择执行时间",
            on_click=pick_datetime,
        )
        time_row = ft.Row(
            [pick_btn, time_display], spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        gs = ft.BorderSide(1, ft.Colors.GREY_300)

        name_field = ft.TextField(
            label="任务内容", value=pending.get("task_name", ""),
            border_color=ft.Colors.GREY_300, dense=True, expand=True,
            multiline=True, min_lines=2, max_lines=4,
            prefix_icon=ft.icons.Icons.TASK_ALT,
        )

        is_periodic = pending.get("is_periodic", False)
        periodic_switch = ft.Switch(label="周期性任务", value=is_periodic)
        period_field = ft.TextField(
            label="周期 (如 1d/2h/30m/1w)",
            value=pending.get("period", ""),
            border_color=ft.Colors.GREY_300,expand=True,
            disabled=not is_periodic,
            
        )

        is_interactive = pending.get("is_interactive", False)
        interactive_switch = ft.Switch(label="交互模式", value=is_interactive)

        status_dd = ft.Dropdown(
            label="任务状态",
            options=[ft.dropdown.Option(key=SubTaskStatus.PENDING.value, text="待处理"),
                     ft.dropdown.Option(key=SubTaskStatus.IN_PROGRESS.value, text="执行中"),
                     ft.dropdown.Option(key=SubTaskStatus.COMPLETED.value, text="已完成"),
                     ft.dropdown.Option(key=SubTaskStatus.FAILED.value, text="已失败"),
                     ft.dropdown.Option(key=SubTaskStatus.SKIPPED.value, text="已跳过")],
            value=pending.get("status", SubTaskStatus.PENDING.value),
            dense=True,
            expand=True,
        )

        def on_periodic_change(e):
            period_field.disabled = not periodic_switch.value
            period_field.update()
        periodic_switch.on_change = on_periodic_change

        def on_save(e):
            updated = dict(pending)
            updated["task_name"] = name_field.value.strip() or "未命名"
            updated["next_execution_time"] = time_data["value"]
            updated["is_periodic"] = periodic_switch.value
            updated["period"] = period_field.value.strip() if periodic_switch.value else ""
            updated["is_interactive"] = interactive_switch.value
            updated["status"] = status_dd.value
            self._save_pending(pending, updated)
            self._close_dialog(dlg)

        def on_delete(e):
            self._close_dialog(dlg)
            self._confirm_delete_pending(pending)

        dlg = ft.AlertDialog(
            bgcolor=self.DIALOG_BGCOLOR,
            shape=ft.RoundedRectangleBorder(radius=3),  # 新增：弹窗整体直角
            content_padding=ft.Padding(20, 10, 20, 4),
            actions_padding=ft.Padding(20, 0, 20, 10),
            title=ft.Row([
                ft.Icon(ft.icons.Icons.EDIT_NOTE, size=20),
                ft.Text("编辑计划任务", size=16, weight=ft.FontWeight.BOLD),
            ]),
            content=ft.Column([
                ft.Column([
                    
                    name_field,
                ], spacing=10),
                ft.Column([
                    ft.Text("执行时间", size=12, color=ft.Colors.GREY_500,
                            weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=time_row,
                        border=ft.Border(top=gs, left=gs, right=gs, bottom=gs),
                        border_radius=1,
                        padding=ft.Padding(left=8, top=0, right=8, bottom=0),
                    ),
                ], spacing=6),
                ft.Column([
                    ft.Text("任务设置", size=12, color=ft.Colors.GREY_500,
                            weight=ft.FontWeight.BOLD),
                    periodic_switch,
                    period_field,
                    interactive_switch,
                    status_dd,
                ], spacing=10),
            ], spacing=16, width=400, tight=True),
            actions=[
                ft.TextButton("删除", on_click=on_delete,
                              style=ft.ButtonStyle(color=ft.Colors.RED)),
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.FilledButton("保存", on_click=on_save),
            ],
        )
        self._open_dialog(dlg)

    # ── 添加任务 ──

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

    def _show_add_task_dialog(self):
        """显示添加任务对话框"""
        attr_mgr = TaskAttributeManager(json_path=self.task_config_file_path)
        categories = attr_mgr.get_categories()
        cat_names = list(categories.keys())
        if not cat_names:
            return

        # ── 级联数据 ──
        current_cat = cat_names[0]
        current_subs = [s[0] for s in categories.get(current_cat, [])]

        # ── 表单数据 ──
        form = {
            "task_type": current_cat,
            "task_sub_type": current_subs[0] if current_subs else "",
            "task_name": "",
            "sub_task_detail": "",
            "next_execution_time": "",
            "project_path": "",
            "is_periodic": False,
            "period": "1d",
            "is_interactive": False,
            "status": SubTaskStatus.PENDING.value,
        }

        # ── 大类下拉 ──
        def on_cat_change(e):
            form["task_type"] = cat_dd.value or ""
            new_subs = [s[0] for s in categories.get(form["task_type"], [])]
            sub_dd.options = [ft.dropdown.Option(key=n, text=n) for n in new_subs]
            if new_subs:
                sub_dd.value = new_subs[0]
                form["task_sub_type"] = new_subs[0]
            else:
                sub_dd.value = None
                form["task_sub_type"] = ""
            dlg.update()

        cat_dd = ft.Dropdown(
            options=[ft.dropdown.Option(key=n, text=n) for n in cat_names],
            value=current_cat,
            dense=True,
            expand=True,
            on_select=on_cat_change,
        )

        # ── 子类下拉 ──
        sub_dd = ft.Dropdown(
            options=[ft.dropdown.Option(key=n, text=n) for n in current_subs],
            value=form["task_sub_type"],
            dense=True,
            expand=True,
        )

        def on_sub_change(e):
            form["task_sub_type"] = sub_dd.value or ""

        sub_dd.on_select = on_sub_change

        # ── 任务名称 ──
        name_field = ft.TextField(
            label="任务名称",
            hint_text="输入任务名称",
            border_color=ft.Colors.GREY_300,
            dense=True,
            expand=True,
        )

        # ── 描述输入 ──
        detail_field = ft.TextField(
            label="任务描述",
            hint_text="简要描述任务内容",
            border_color=ft.Colors.GREY_300,
            prefix_icon=ft.Icons.TASK_ALT,
            multiline=True,
            expand=True,
            min_lines=2,
            max_lines=4,
            dense=True,
        )

        # ── 时间选择 ──
        time_data = {"value": ""}
        time_display = ft.Text(
            "点击选择执行时间",
            size=13,
            color=ft.Colors.GREY_400,
            italic=True,
            expand=True,
        )
        picker_ref = ft.Ref[ft.CupertinoDatePicker]()
        time_dialog = None

        def confirm_datetime(_):
            nonlocal time_dialog
            p = picker_ref.current
            if p and p.value:
                time_data["value"] = p.value.strftime("%Y-%m-%d %H:%M:%S")
                time_display.value = time_data["value"]
                time_display.color = ft.Colors.GREY_700
                time_display.italic = False
                time_display.update()
            if time_dialog:
                time_dialog.open = False
            self.page.update()

        def pick_datetime(_):
            nonlocal time_dialog
            time_dialog = ft.AlertDialog(
                title=ft.Text("选择执行时间"),
                content=ft.Container(
                    content=ft.CupertinoDatePicker(
                        ref=picker_ref,
                        value=datetime.now(),
                        use_24h_format=True,
                        date_picker_mode=ft.CupertinoDatePickerMode.DATE_AND_TIME,
                        minute_interval=1,
                    ),
                    height=220,
                ),
                actions=[ft.TextButton("确定", on_click=confirm_datetime)],
            )
            self.page.show_dialog(time_dialog)

        pick_btn = ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            tooltip="选择执行时间",
            icon_size=18,
            on_click=pick_datetime,
        )

        # ── 项目路径 ──
        path_field = ft.TextField(
            label="项目路径",
            hint_text="选择项目文件夹（必填）",
            dense=True,
            read_only=True,
            border_color=ft.Colors.GREY_300,
            prefix_icon=ft.Icons.FOLDER_OPEN,
            expand=True,
        )

        def pick_project(_):
            import subprocess
            try:
                result = subprocess.run(
                    ["zenity", "--file-selection", "--directory",
                     "--title=选择项目文件夹"],
                    capture_output=True, text=True, timeout=30)
                if result.returncode == 0 and result.stdout.strip():
                    path_field.value = result.stdout.strip()
                    path_field.update()
            except Exception:
                pass

        path_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="选择文件夹",
            icon_size=18,
            on_click=pick_project,
        )

        path_error = ft.Text(
            "",
            size=11,
            color=ft.Colors.RED_400,
            visible=False,
        )

        gs = ft.BorderSide(1, ft.Colors.GREY_300)

        # ── 周期开关 ──
        def on_periodic_change(e):
            form["is_periodic"] = e.control.value

        periodic_switch = ft.Switch(
            label="周期任务",
            value=False,
            on_change=on_periodic_change,
        )

        period_field = ft.TextField(
            label="周期间隔",
            hint_text="如 1d / 12h / 30m",
            value="1d",
            dense=True,
            visible=False,
        )

        def on_periodic_change_ui(e):
            form["is_periodic"] = e.control.value
            period_field.visible = e.control.value
            period_field.update()
            self.page.update()

        periodic_switch.on_change = on_periodic_change_ui

        # ── 交互开关 ──
        def on_interactive_change(e):
            form["is_interactive"] = e.control.value

        interactive_switch = ft.Switch(
            label="交互模式",
            value=False,
            on_change=on_interactive_change,
        )

        # ── 状态下拉 ──
        status_dd = ft.Dropdown(
            label="任务状态",
            options=[ft.dropdown.Option(key=SubTaskStatus.PENDING.value, text="待处理"),
                     ft.dropdown.Option(key=SubTaskStatus.IN_PROGRESS.value, text="执行中"),
                     ft.dropdown.Option(key=SubTaskStatus.COMPLETED.value, text="已完成"),
                     ft.dropdown.Option(key=SubTaskStatus.FAILED.value, text="已失败"),
                     ft.dropdown.Option(key=SubTaskStatus.SKIPPED.value, text="已跳过")],
            value=SubTaskStatus.PENDING.value,
            dense=True,
            expand=True,
        )

        # ── 保存 ──
        def on_save(e):
            if not path_field.value:
                path_error.value = "请选择项目路径"
                path_error.visible = True
                dlg.update()
                return
            form["task_name"] = name_field.value or ""
            form["sub_task_detail"] = detail_field.value or ""
            form["next_execution_time"] = time_data["value"]
            form["project_path"] = path_field.value or ""
            form["period"] = period_field.value or "1d"
            form["status"] = status_dd.value
            self._close_dialog(dlg)
            self._save_new_task(form)

        # ── 组装对话框 ──
        dlg = ft.AlertDialog(
            bgcolor=self.DIALOG_BGCOLOR,
            shape=ft.RoundedRectangleBorder(radius=3),
            content_padding=ft.Padding(20, 10, 20, 4),
            actions_padding=ft.Padding(20, 0, 20, 10),
            title=ft.Row([
                ft.Icon(ft.Icons.ADD_TASK, size=20),
                ft.Text("添加任务", size=16, weight=ft.FontWeight.BOLD),
            ]),
            content=ft.Column([
                ft.Column([
                    ft.Text("任务类型", size=12, color=ft.Colors.GREY_500,
                            weight=ft.FontWeight.BOLD),
                    ft.Row([cat_dd, sub_dd], spacing=8),
                ], spacing=6),
                ft.Column([
                    ft.Text("任务描述", size=12, color=ft.Colors.GREY_500,
                            weight=ft.FontWeight.BOLD),
                    name_field,
                    detail_field,
                ], spacing=10),
                ft.Column([
                    ft.Text("执行时间", size=12, color=ft.Colors.GREY_500,
                            weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.Row([time_display, pick_btn], spacing=8,
                                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        border=ft.Border(top=gs, left=gs, right=gs, bottom=gs),
                        border_radius=1,
                        padding=ft.Padding(left=8, top=0, right=8, bottom=0),
                    ),
                ], spacing=6),
                ft.Column([
                    ft.Text("项目路径", size=12, color=ft.Colors.GREY_500,
                            weight=ft.FontWeight.BOLD),
                    ft.Row([path_field, path_btn], spacing=4),
                    path_error,
                ], spacing=6),
                ft.Column([
                    ft.Text("任务设置", size=12, color=ft.Colors.GREY_500,
                            weight=ft.FontWeight.BOLD),
                    periodic_switch,
                    period_field,
                    interactive_switch,
                    status_dd,
                ], spacing=10),
            ], spacing=16, width=400, tight=True, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.FilledButton("保存", on_click=on_save),
            ],
        )
        self._open_dialog(dlg)
