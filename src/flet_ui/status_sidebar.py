"""任务状态侧边栏 —— 展示当前任务（state 文件）和计划任务（task_{ts}.json）"""

import json, os, subprocess, platform
import flet as ft
from task_attribute_manager import TaskAttributeManager
from task_manager import TaskManager


class StatusSidebar:
    """左侧任务状态面板"""

    WIDTH: int = 280
    BGCOLOR = ft.Colors.GREY_50
    TITLE_BGCOLOR = ft.Colors.BLUE_GREY_50
    DIALOG_BGCOLOR = ft.Colors.WHITE
    TITLE: str = "任务状态"
    EMPTY_TEXT: str = "暂无任务"

    STATUS_COLORS = {
        "completed": ft.Colors.GREEN,
        "in_progress": ft.Colors.BLUE,
        "failed": ft.Colors.RED,
        "pending": ft.Colors.ORANGE,
    }
    STATUS_LABELS = {
        "completed": "已完成",
        "in_progress": "进行中",
        "failed": "失败",
        "pending": "待执行",
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

        self._list.controls.clear()

        has_any = tasks or pending or chat_tasks
        if not has_any:
            self._list.controls.append(
                ft.Text(self.EMPTY_TEXT, size=12, color=ft.Colors.GREY_400, italic=True))
        else:
            # 历史任务
            if tasks:
                self._list.controls.append(
                    ft.Text("历史任务", size=11, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_500))
                for t in tasks:
                    self._list.controls.append(self._task_card(t))
            # 计划任务
            if pending:
                if tasks or chat_tasks:
                    self._list.controls.append(ft.Divider(height=1, color=ft.Colors.GREY_300))
                self._list.controls.append(
                    ft.Text("计划任务", size=11, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_500))
                for idx, p in enumerate(pending):
                    self._list.controls.append(self._pending_card(p, idx))

        self.page.update()

    # ── 内部构建 ──

    def _build(self):
        self._list = ft.ListView(spacing=6, padding=ft.Padding(8, 4, 8, 4), expand=True)
        def _on_panel_click(e):
            if not self._selected_key:
                return
            self._selected_key = ""
            self._needs_refresh = True
            self.refresh()
            if self._default_work_dir and self._on_chat_select:
                self._on_chat_select(self._default_work_dir, "")
        content_col = ft.Column([
            self._build_title_bar(),
            ft.Container(content=self._list, expand=True),
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
        title_row = [ft.Text(self.TITLE, weight=ft.FontWeight.W_600, size=13)]
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
        status = task.get("status", "pending")
        pp = task.get("project_path", "")
        state_file = task.get("state_file", "")
        key = state_file
        selected = (self._selected_key == key)
        menu_items = [
            ft.PopupMenuItem(content=ft.Text("删除", size=14),
                             on_click=lambda e, t=task: self._confirm_delete_task(t)),
        ]
        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Row([
                        ft.Text("●" if selected else "○", size=14,
                                color=ft.Colors.BLUE if selected else ft.Colors.GREY_400),
                        ft.Text(name, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True,
                                color=ft.Colors.BLACK87 if selected else ft.Colors.GREY_700),
                        self._status_badge(status),
                    ], spacing=4, expand=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], expand=True),
                ft.PopupMenuButton(items=menu_items, icon_size=16),
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=ft.Colors.WHITE, border_radius=6,
            padding=ft.Padding(8, 6, 4, 6),
            border=self._card_border(),
            on_click=lambda e, k=key, p=pp, s=state_file: self._select_card(k, p, s),
        )

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
        periodic = " 🔁" if pending.get("is_periodic") else ""
        status = pending.get("status", "pending")

        header = ft.Row([
            ft.Column([
                ft.Text(name + periodic, size=12, weight=ft.FontWeight.W_500,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(f"执行: {exec_time[:16]}", size=10, color=ft.Colors.GREY_500),
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
        """保存编辑后的计划任务到 task_{ts}.json"""
        file_path = pending.get("file", "")
        if not file_path or not os.path.exists(file_path):
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            s = data.get("subtask", {})
            s["sub_task_name"] = updated.get("task_name", s.get("sub_task_name", ""))
            s["next_execution_time"] = updated.get("next_execution_time", "")
            s["is_periodic"] = updated.get("is_periodic", False)
            s["period"] = updated.get("period", "")
            s["is_interactive"] = updated.get("is_interactive", False)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, IOError):
            pass
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

        def on_date_picked(e):
            dp = e.control
            if dp.value:
                selected_date = dp.value.isoformat()
                self._remove_overlay(dp)
                tp = ft.TimePicker(
                    on_change=lambda te: on_time_picked(te, selected_date),
                    on_dismiss=lambda _: self._remove_overlay(tp),
                )
                self.page.overlay.append(tp)
                tp.open = True
                self.page.update()
            else:
                self._remove_overlay(dp)

        def on_time_picked(te, selected_date):
            tp = te.control
            if tp.value:
                time_data["value"] = f"{selected_date}T{tp.value.isoformat()}"
                time_display.value = time_data["value"]
                time_display.color = ft.Colors.GREY_700
                time_display.italic = False
                time_display.update()
            self._remove_overlay(tp)

        def pick_datetime(_):
            dp = ft.DatePicker(
                on_change=on_date_picked,
                on_dismiss=lambda _: self._remove_overlay(dp),
            )
            self.page.overlay.append(dp)
            dp.open = True
            self.page.update()

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
