"""任务状态侧边栏 —— 展示当前任务（state 文件）和计划任务（pending_tasks.json）"""

import json, os, glob
import flet as ft


class StatusSidebar:
    """左侧任务状态面板"""

    WIDTH: int = 220
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
                for p in pending:
                    self._list.controls.append(self._pending_card(p))

        self.page.update()

    # ── 内部构建 ──

    def _build(self):
        self._list = ft.ListView(spacing=6, padding=ft.Padding(8, 4, 8, 4), expand=True)
        self._panel = ft.Container(
            visible=self._visible,
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
                tasks.append({
                    "name": mt.get("main_task_name", "未知任务"),
                    "status": mt.get("status", "pending"),
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

        rows = [
            ft.Text(desc, size=12, weight=ft.FontWeight.W_500, max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Row([self._status_badge(task["status"])], spacing=4),
        ]
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
        )

    def _pending_card(self, pending: dict) -> ft.Container:
        name = pending.get("task_name", "未知")[:36]
        if len(pending.get("task_name", "")) > 36:
            name += "…"
        exec_time = pending.get("next_execution_time", "")
        periodic = " 🔁" if pending.get("is_periodic") else ""

        return ft.Container(
            content=ft.Column([
                ft.Text(name + periodic, size=12, weight=ft.FontWeight.W_500,
                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(f"执行: {exec_time[:16]}", size=10, color=ft.Colors.GREY_500),
            ], spacing=2),
            bgcolor=ft.Colors.WHITE, border_radius=6,
            padding=ft.Padding(8, 6, 8, 6),
            border=self._card_border(),
        )
