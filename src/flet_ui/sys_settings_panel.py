"""系统设置面板 UI 组件"""

import subprocess
import flet as ft


class SystemSettingsPanel:
    """系统设置面板 —— 执行/日志/安全配置"""

    PANEL_WIDTH: int = 480
    PANEL_HEIGHT: int = 420
    PANEL_BGCOLOR = ft.Colors.WHITE
    TITLE_BGCOLOR = ft.Colors.GREY_100
    BORDER_RADIUS: int = 10
    SHADOW = ft.BoxShadow(spread_radius=1, blur_radius=12, color=ft.Colors.BLACK26)
    LABEL_COLOR = ft.Colors.GREY_700

    TITLE_TEXT: str = "🔧 系统配置"
    SECTION_EXEC: str = "执行"
    SECTION_LOG: str = "日志"
    SECTION_SECURITY: str = "安全"
    WORK_DIR_LABEL: str = "工作目录:"
    SAVE_LABEL: str = "保存"
    SAVE_FAIL_TITLE: str = "保存失败"
    CLOSE_TOOLTIP: str = "关闭"
    PICK_DIR_TOOLTIP: str = "选择目录"

    TF_DEFAULTS: dict = {"dense": True, "text_size": 13, "border_color": ft.Colors.GREY_300}

    def __init__(self, page: ft.Page, config, system: str = "linux"):
        self.page = page
        self.config = config
        self._system = system
        self._build()

    @property
    def panel(self) -> ft.Container:
        return self._panel

    @property
    def content_body(self) -> ft.Column:
        return self._content_body

    def open(self):
        self._panel.visible = True
        self.page.update()

    def close(self):
        self._panel.visible = False
        self.page.update()

    # ── 构建 ──

    def _build(self):
        cfg = self.config
        tf = self.TF_DEFAULTS

        self._sys_timeout = ft.TextField(label="超时(秒)", value=str(cfg.execution.timeout), width=80, **tf)
        self._sys_mem_en = ft.Switch(label="启用记忆", height=30, value=cfg.execution.memory_enabled)
        self._sys_rounds = ft.TextField(label="调用上限", value=str(cfg.execution.max_rounds), width=100, **tf)
        self._sys_work_dir = ft.TextField(value=cfg.execution.work_dir, read_only=True, **tf)
        self._sys_enable_history = ft.Switch(label="历史任务关联", height=30,
            value=cfg.execution.enable_history_task_association)
        self._sys_log_enabled = ft.Switch(label="启用日志", height=30, value=cfg.log.enabled)
        self._sys_log_history = ft.Switch(label="记录历史", height=30, value=cfg.log.history)
        self._sys_auth_interactive = ft.Switch(label="交互模式", height=30, value=cfg.auth.interactive)
        self._sys_auth_sensitive = ft.Switch(label="敏感命令检查", height=30,
            value=cfg.auth.sensitive_command_check)

        self._content_body = ft.Column([
            ft.Text(self.SECTION_EXEC, weight=ft.FontWeight.W_600, size=16, color=self.LABEL_COLOR),
            ft.Row([
                ft.Text(self.WORK_DIR_LABEL, size=14), self._sys_work_dir,
                ft.IconButton(icon=ft.Icons.FOLDER_OPEN, icon_size=18, tooltip=self.PICK_DIR_TOOLTIP, on_click=lambda e: self._pick_dir()),
            ], spacing=4),
            ft.Row([
                self._sys_timeout, self._sys_rounds,
            ], spacing=24),
            ft.Row([self._sys_mem_en, self._sys_enable_history], spacing=24),
            ft.Divider(height=1),
            ft.Text(self.SECTION_LOG, weight=ft.FontWeight.W_600, size=16, color=self.LABEL_COLOR),
            ft.Row([self._sys_log_enabled, self._sys_log_history], spacing=24, wrap=True),
            ft.Divider(height=1),
            ft.Text(self.SECTION_SECURITY, weight=ft.FontWeight.W_600, size=16, color=self.LABEL_COLOR),
            ft.Row([self._sys_auth_interactive, self._sys_auth_sensitive], spacing=24, wrap=True),
            ft.Container(expand=True),
            ft.Container(content=ft.Row([
                ft.ElevatedButton(self.SAVE_LABEL, on_click=self._save, height=32),
            ], alignment=ft.MainAxisAlignment.END)),
        ], spacing=16, expand=True)

        self._panel = ft.Container(
            opacity=1.0, width=self.PANEL_WIDTH, height=self.PANEL_HEIGHT,
            border_radius=ft.BorderRadius(self.BORDER_RADIUS, self.BORDER_RADIUS, self.BORDER_RADIUS, self.BORDER_RADIUS),
            bgcolor=self.PANEL_BGCOLOR,
            shadow=self.SHADOW,
            left=180, top=60, visible=False,
            content=ft.Column([
                ft.Container(content=ft.Row([
                    ft.Text(self.TITLE_TEXT, weight=ft.FontWeight.W_600, size=14),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip=self.CLOSE_TOOLTIP, on_click=lambda e: self.close()),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.Padding(16, 7, 10, 7), bgcolor=self.TITLE_BGCOLOR,
                    border_radius=ft.BorderRadius(self.BORDER_RADIUS, self.BORDER_RADIUS, 0, 0),
                ),
                ft.Container(content=self._content_body, expand=True, padding=ft.Padding(16, 12, 16, 12)),
            ], spacing=0, expand=True),
        )

    # ── 目录选择 ──

    def _pick_dir(self):
        if self._system == "windows":
            import ctypes
            from ctypes import wintypes
            BIF_RETURNONLYFSDIRS = 0x00000001
            pidl = ctypes.windll.shell32.SHBrowseForFolderW(
                ctypes.byref(wintypes.HWND()), None, BIF_RETURNONLYFSDIRS,
            )
            if pidl:
                buf = ctypes.create_unicode_buffer(260)
                ctypes.windll.shell32.SHGetPathFromIDListW(pidl, buf)
                ctypes.windll.ole32.CoTaskMemFree(pidl)
                path = buf.value
                if path:
                    self._sys_work_dir.value = path
                    self.page.update()
        else:
            r = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title=选择工作目录"],
                capture_output=True, text=True,
            )
            path = r.stdout.strip()
            if path:
                self._sys_work_dir.value = path
                self.page.update()

    # ── 保存 ──

    def _save(self, e):
        try:
            cfg = self.config
            cfg.execution.timeout = int(self._sys_timeout.value)
            cfg.execution.max_rounds = int(self._sys_rounds.value)
            cfg.execution.memory_enabled = self._sys_mem_en.value
            cfg.execution.work_dir = self._sys_work_dir.value.strip()
            cfg.execution.enable_history_task_association = self._sys_enable_history.value
            cfg.log.enabled = self._sys_log_enabled.value
            cfg.log.history = self._sys_log_history.value
            cfg.auth.interactive = self._sys_auth_interactive.value
            cfg.auth.sensitive_command_check = self._sys_auth_sensitive.value
            cfg.save()
            self.close()
        except Exception as ex:
            self.page.show_dialog(ft.AlertDialog(shape=ft.RoundedRectangleBorder(radius=3), content_padding=ft.Padding(20, 20, 20, 20),
                title=ft.Text(self.SAVE_FAIL_TITLE), content=ft.Text(str(ex)),
            ))
