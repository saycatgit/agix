"""任务状态侧边栏 —— 展示当前任务（state 文件）和计划任务（pending_tasks.json）"""

import json, os, glob, subprocess, platform
import flet as ft


class StatusSidebar:
    """左侧任务状态面板"""

    WIDTH: int = 190
    BGCOLOR = ft.Colors.GREY_50
    TITLE_BGCOLOR = ft.Colors.BLUE_GREY_50
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

    def __init__(self, page: ft.Page, task_dir: str, visible: bool = True, extra_controls: list = None):
        self.page = page
        self.task_dir = task_dir
        self._visible = visible
        self._extra_controls = extra_controls or []
        self._build()

    @property
    def container(self) -> ft.Container:
        return self._panel

    @property
    def visible(self) -> bool:
        return self._panel.visible

    def toggle(self):
        self._panel.visible = not self._panel.visible
        if self._panel.visible:
            self.refresh()
        self.page.update()

    def refresh(self):
        tasks, pending = self._load_all()
        self._list.controls.clear()

        if not tasks and not pending:
            self._list.controls.append(
                ft.Text(self.EMPTY_TEXT, size=12, color=ft.Colors.GREY_400, italic=True))
        else:
            if tasks:
                self._list.controls.append(
                    ft.Text("历史任务", size=11, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_500))
                for t in tasks:
                    self._list.controls.append(self._task_card(t))

            if pending:
                if tasks:
                    self._list.controls.append(ft.Divider(height=1, color=ft.Colors.GREY_300))
                self._list.controls.append(
                    ft.Text("计划任务", size=11, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_500))
                for idx, p in enumerate(pending):
                    self._list.controls.append(self._pending_card(p, idx))

        self.page.update()

    # ── 内部构建 ──

    def _build(self):
        self._list = ft.ListView(spacing=6, padding=ft.Padding(8, 4, 8, 4), expand=True)
        self._panel = ft.Container(
            visible=self._visible,
            expand_loose=True,
            width=self.WIDTH,
            bgcolor=self.BGCOLOR,
            content=ft.Column([
                self._build_title_bar(),
                ft.Container(content=self._list, expand=True),
            ], spacing=0, expand=True),
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
        tasks = []
        pattern = os.path.join(self.task_dir, "task_*_state.json")
        for fpath in sorted(glob.glob(pattern), reverse=True):
            try:
                with open(fpath, "r") as f:
                    data = json.load(f)
                mt = data.get("maintask", {})
                subtasks = data.get("subtasks", [])
                # 汇总各 phase 步骤
                in_progress_subtasks = []
                for s in subtasks:
                    if s.get("status") != "in_progress":
                        continue
                    sub_phases = []
                    for phase, steps in s.get("plan_steps", {}).items():
                        done = sum(1 for st in steps if st.get("status") == "completed")
                        sub_phases.append({"name": phase, "done": done, "total": len(steps)})
                    in_progress_subtasks.append({
                        "name": s.get("sub_task_name", "未知子任务"),
                        "phases": sub_phases,
                    })
                # 只有至少一个 subtask 的 project_path 目录存在时才显示
                valid_paths = [s.get("project_path", "") for s in subtasks
                               if s.get("project_path") and os.path.isdir(s.get("project_path", ""))]
                if not valid_paths:
                    continue
                tasks.append({
                    "name": mt.get("main_task_name", "未知任务"),
                    "status": mt.get("status", "pending"),
                    "state_file": fpath,
                    "project_paths": valid_paths,
                    "created_at": mt.get("created_at", ""),
                    "in_progress_subtasks": in_progress_subtasks,
                })
            except (json.JSONDecodeError, IOError):
                continue

        pending_path = os.path.join(self.task_dir, "pending_tasks.json")
        pending = []
        try:
            if os.path.exists(pending_path):
                with open(pending_path, "r") as f:
                    pending = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

        return tasks, pending

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
        desc = task["name"][:36] + ("…" if len(task["name"]) > 36 else "")

        header = ft.Row([
            ft.Column([
                ft.Text(desc, size=12, weight=ft.FontWeight.W_500, max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Row([self._status_badge(task["status"])], spacing=4),
            ], expand=True, spacing=2),
        ], spacing=4)

        rows = [header]
        for sub in task.get("in_progress_subtasks", []):
            rows.append(ft.Text(f"▸ {sub['name']}",
                                size=11, weight=ft.FontWeight.W_500,
                                color=ft.Colors.BLUE_700))
            for ph in sub.get("phases", []):
                rows.append(ft.Text(f"    {ph['name']}: {ph['done']}/{ph['total']}",
                                    size=10, color=ft.Colors.BLUE_GREY_400))

        return ft.Container(
            content=ft.Column(rows, spacing=4),
            bgcolor=ft.Colors.WHITE, border_radius=6,
            padding=ft.Padding(8, 6, 8, 6),
            border=self._card_border(),
            on_click=lambda e: self._open_project(task),
        )

    def _pending_card(self, pending: dict, idx: int) -> ft.Container:
        name = pending.get("task_name", "未知")[:36]
        if len(pending.get("task_name", "")) > 36:
            name += "…"
        exec_time = pending.get("next_execution_time", "")
        periodic = " 🔁" if pending.get("is_periodic") else ""

        header = ft.Row([
            ft.Column([
                ft.Text(name + periodic, size=12, weight=ft.FontWeight.W_500,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(f"执行: {exec_time[:16]}", size=10, color=ft.Colors.GREY_500),
            ], expand=True, spacing=2),
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

    def _remove_overlay(self, control):
        try:
            self.page.overlay.remove(control)
            self.page.update()
        except (ValueError, AssertionError):
            pass

    def _show_task_menu(self, task: dict):
        dlg = ft.AlertDialog(
            title=ft.Text("操作"),
            content=ft.Column([
                ft.TextButton("打开文件夹", on_click=lambda e: self._open_project_and_close(task, dlg)),
                ft.TextButton("删除任务", on_click=lambda e: self._confirm_delete_and_close(task, dlg)),
            ], tight=True, spacing=0),
        )
        self._open_dialog(dlg)

    def _show_pending_menu(self, pending: dict, idx: int):
        dlg = ft.AlertDialog(
            title=ft.Text("操作"),
            content=ft.Column([
                ft.TextButton("删除任务", on_click=lambda e: self._confirm_delete_pending_and_close(pending, idx, dlg)),
            ], tight=True, spacing=0),
        )
        self._open_dialog(dlg)

    def _open_project_and_close(self, task: dict, dlg: ft.AlertDialog):
        self._open_project(task)
        self._close_dialog(dlg)

    def _confirm_delete_and_close(self, task: dict, dlg: ft.AlertDialog):
        self._close_dialog(dlg)
        self._confirm_delete_task(task)

    def _confirm_delete_pending_and_close(self, pending: dict, idx: int, dlg: ft.AlertDialog):
        self._close_dialog(dlg)
        self._confirm_delete_pending(pending, idx)

    def _open_project(self, task: dict):
        """在系统文件管理器中打开项目文件夹"""
        paths = task.get("project_paths", [])
        if not paths:
            return
        path = paths[0]
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
            title=ft.Text("确认删除"),
            content=ft.Text(f"确定删除项目「{name}」的记录吗？\n\n项目文件夹不会被删除。"),
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

    def _confirm_delete_pending(self, pending: dict, idx: int):
        """弹出确认对话框后从 pending_tasks.json 中删除计划任务"""
        def on_yes(e):
            self._close_dialog(dlg)
            self._delete_pending(idx)

        def on_no(e):
            self._close_dialog(dlg)

        name = pending.get("task_name", "未知")[:30]
        dlg = ft.AlertDialog(
            title=ft.Text("确认删除"),
            content=ft.Text(f"确定删除计划任务「{name}」吗？"),
            actions=[
                ft.TextButton("取消", on_click=on_no),
                ft.TextButton("删除", on_click=on_yes),
            ],
        )
        self._open_dialog(dlg)

    def _delete_pending(self, idx: int):
        pending_path = os.path.join(self.task_dir, "pending_tasks.json")
        if os.path.exists(pending_path):
            with open(pending_path, "r") as f:
                pending_list = json.load(f)
            if 0 <= idx < len(pending_list):
                pending_list.pop(idx)
                with open(pending_path, "w") as f:
                    json.dump(pending_list, f, ensure_ascii=False, indent=2)
        self.refresh()

    def _save_pending(self, idx: int, updated: dict):
        """保存编辑后的计划任务到 pending_tasks.json"""
        pending_path = os.path.join(self.task_dir, "pending_tasks.json")
        if os.path.exists(pending_path):
            with open(pending_path, "r") as f:
                pending_list = json.load(f)
            if 0 <= idx < len(pending_list):
                # 保留 id 和 created_at 不被覆盖
                updated["id"] = pending_list[idx].get("id", "")
                updated["created_at"] = pending_list[idx].get("created_at", "")
                pending_list[idx] = updated
                with open(pending_path, "w") as f:
                    json.dump(pending_list, f, ensure_ascii=False, indent=2)
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
            label="任务名称", value=pending.get("task_name", ""),
            border_color=ft.Colors.GREY_400, dense=True,
            prefix_icon=ft.icons.Icons.TASK_ALT,
        )

        is_periodic = pending.get("is_periodic", False)
        periodic_switch = ft.Switch(label="周期性任务", value=is_periodic)
        period_field = ft.TextField(
            label="周期 (如 1d/2h/30m/1w)",
            value=pending.get("period", ""),
            border_color=ft.Colors.GREY_400, dense=True,
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
            self._save_pending(idx, updated)
            self._close_dialog(dlg)

        def on_delete(e):
            self._close_dialog(dlg)
            self._confirm_delete_pending(pending, idx)

        dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.icons.Icons.EDIT_NOTE, size=20),
                ft.Text("编辑计划任务", size=16, weight=ft.FontWeight.BOLD),
            ]),
            content=ft.Column([
                ft.Text("基本信息", size=12, color=ft.Colors.GREY_500,
                        weight=ft.FontWeight.BOLD),
                name_field,
                ft.Text("执行时间", size=12, color=ft.Colors.GREY_500,
                        weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=time_row,
                    border=ft.Border(top=gs, left=gs, right=gs, bottom=gs),
                    border_radius=6,
                    padding=ft.Padding(left=8, top=4, right=8, bottom=4),
                ),
                ft.Divider(height=1, opacity=0.3),
                ft.Text("任务设置", size=12, color=ft.Colors.GREY_500,
                        weight=ft.FontWeight.BOLD),
                periodic_switch,
                period_field,
                interactive_switch,
            ], tight=True, spacing=10, width=380),
            actions=[
                ft.TextButton("删除", on_click=on_delete,
                              style=ft.ButtonStyle(color=ft.Colors.RED)),
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.FilledButton("保存", on_click=on_save),
            ],
        )
        self._open_dialog(dlg)
