"""统一设置面板 UI 组件 —— 左侧分类导航 + 右侧内容区"""

import flet as ft


class UnifiedSettingsPanel:
    """统一设置面板：整合模型设置、系统设置、任务设置"""

    PANEL_WIDTH: int = 960
    PANEL_HEIGHT: int = 620
    PANEL_BGCOLOR = ft.Colors.WHITE
    TITLE_BGCOLOR = ft.Colors.GREY_100
    SIDEBAR_BGCOLOR = ft.Colors.GREY_50
    DIVIDER_COLOR = ft.Colors.GREY_300
    BORDER_RADIUS: int = 10
    SHADOW = ft.BoxShadow(spread_radius=1, blur_radius=12, color=ft.Colors.BLACK26)

    TABS: list = [
        ("模型设置", "⚙"),
        ("系统设置", "🔧"),
        ("任务设置", "📋"),
        ("连接管理", "🔗"),
        ("关于", "ℹ️"),
    ]

    def __init__(self, page: ft.Page, model_settings_panel, sys_settings_panel, task_config_panel, connection_panel, about_panel):
        self.page = page
        self._panels = {
            "模型设置": model_settings_panel,
            "系统设置": sys_settings_panel,
            "任务设置": task_config_panel,
            "连接管理": connection_panel,
            "关于": about_panel,
        }
        self._active_tab = "模型设置"
        self._build()

    @property
    def panel(self) -> ft.Container:
        return self._panel

    def open(self):
        self._switch_tab(self._active_tab)
        self._panel.visible = True
        self.page.update()

    def close(self, e=None):
        self._panel.visible = False
        self._right_content.content = None
        self.page.update()

    # ── 切换 tab ──

    def _switch_tab(self, tab_name: str):
        self._active_tab = tab_name
        for btn in self._nav_btns:
            is_active = btn.data == tab_name
            btn.style = ft.ButtonStyle(
                color=ft.Colors.BLUE if is_active else ft.Colors.GREY_700,
                bgcolor=ft.Colors.BLUE_50 if is_active else None,
                padding=ft.Padding(8, 4, 8, 4),
            )
        panel = self._panels[tab_name]
        self._right_content.content = panel.content_body
        self.page.update()

    # ── 构建 ──

    def _build(self):
        self._nav_btns = []
        for name, icon in self.TABS:
            btn = ft.TextButton(
                f"{icon}  {name}",
                data=name,
                style=ft.ButtonStyle(color=ft.Colors.GREY_700, padding=ft.Padding(8, 4, 8, 4)),
                on_click=lambda e, n=name: self._switch_tab(n),
            )
            self._nav_btns.append(btn)

        nav_col = ft.Column(self._nav_btns, spacing=1, alignment=ft.MainAxisAlignment.START)

        self._right_content = ft.Container(expand=True)
        self._right_content.padding = ft.Padding(8, 8, 8, 8)

        self._panel = ft.Container(
            width=self.PANEL_WIDTH, height=self.PANEL_HEIGHT,
            border_radius=ft.BorderRadius(self.BORDER_RADIUS, self.BORDER_RADIUS, self.BORDER_RADIUS, self.BORDER_RADIUS),
            bgcolor=self.PANEL_BGCOLOR, shadow=self.SHADOW,
            left=120, top=40, visible=False,
            content=ft.Column([
                ft.Container(content=ft.Row([
                    ft.Text("设置", weight=ft.FontWeight.W_600, size=14),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="关闭", on_click=self.close),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.Padding(16, 7, 10, 7), bgcolor=self.TITLE_BGCOLOR,
                    border_radius=ft.BorderRadius(self.BORDER_RADIUS, self.BORDER_RADIUS, 0, 0),
                ),
                ft.Container(content=ft.Row([
                    ft.Container(content=nav_col, width=130, bgcolor=self.SIDEBAR_BGCOLOR,
                        padding=ft.Padding(8, 8, 8, 8)),
                    ft.VerticalDivider(width=1, color=self.DIVIDER_COLOR),
                    self._right_content,
                ], spacing=0), expand=True),
            ], spacing=0, expand=True),
        )
