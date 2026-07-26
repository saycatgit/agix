"""Flet UI 主模块 —— Agix 桌面界面（类封装版）"""

import asyncio, os, uuid, subprocess, webbrowser, flet as ft
from flet_ui.task_panel import TaskPanel
from flet_ui.chat_panel import ChatPanel
from flet_ui.status_sidebar import StatusSidebar
from flet_ui.model_settings_panel import ModelSettingsPanel
from flet_ui.sys_settings_panel import SystemSettingsPanel
from flet_ui.task_config_panel import TaskConfigPanel
from flet_ui.unified_settings_panel import UnifiedSettingsPanel
from flet_ui.connection_settings_panel import ConnectionSettingsPanel
from flet_ui.about_panel import AboutPanel
from event_queue_manager import EventQueueManager
from meta import MsgType, MsgField, MsgStyle, TaskField
from llm_client import PROVIDERS
from task_manager import TaskManager
MsgStyle.STATUS = "status"; MsgStyle.ACTION = "action"; MsgStyle.THINKING = "thinking"; MsgStyle.DEBUG = "debug"

_STYLE_VISUALS = {
    MsgStyle.USER:      {"bg": ft.Colors.GREEN_50,"size":16},
    MsgStyle.ASSISTANT: {"bg": ft.Colors.DEEP_ORANGE_50,"size":16},
    MsgStyle.ASK:       {"bg": ft.Colors.ORANGE_50},
    MsgStyle.ERROR:     {"bg": ft.Colors.RED_50},
    MsgStyle.WARN:      {"bg": ft.Colors.AMBER_50},
    MsgStyle.STATUS:    {"bg": ft.Colors.BLUE_50},
    MsgStyle.ACTION:    {"bg": ft.Colors.TEAL_50},
    MsgStyle.THINKING:  {"bg": ft.Colors.YELLOW_50},
    MsgStyle.DEBUG:     {"bg": ft.Colors.PINK_50},
    # MsgStyle.THINKING:  {"bg": ft.Colors.PURPLE_50, "italic": True, "size": 12},
}

_AVATAR_DATA = {
    MsgStyle.USER:      ("👤", None),
    MsgStyle.ASSISTANT: ("👾", None),
    MsgStyle.ASK:       ("🔍",  None),
    MsgStyle.ERROR:     ("⚠️",  None),
    MsgStyle.WARN:      ("⚡", None),
    MsgStyle.STATUS:    ("📊", None),
    MsgStyle.ACTION:    ("🔧",  None),
    MsgStyle.THINKING:  ("🧠", None),
    MsgStyle.DEBUG:     ("🐛", None),
}

class AgixUI:
    """Agix 桌面 UI 管理器"""
    def __init__(self, page: ft.Page, eqm: EventQueueManager, agent):
        self.page = page; self.eqm = eqm; self.agent = agent
        self._task_ticks = [0]; self._max_btn_ref = ft.Ref[ft.IconButton]()

        # 子面板
        self.task_panel = TaskPanel(
            page, eqm, _STYLE_VISUALS, MsgStyle,
            on_close=lambda: setattr(self.task_switch, 'value', False),
            thinking_enabled=agent.config.execution.thinking,
        )
        self._build_lights_and_switch()
        self.chat_panel = ChatPanel(
            page, eqm, agent, _STYLE_VISUALS, _AVATAR_DATA, MsgStyle, MsgType, PROVIDERS,
        )
        self.page.on_keyboard_event = self._global_keyboard
        self.model_settings_panel = ModelSettingsPanel(page, agent.config, PROVIDERS)
        self.sys_settings_panel = SystemSettingsPanel(page, agent.config)
        self.task_config_panel = TaskConfigPanel(page, agent.config)
        self.connection_panel = ConnectionSettingsPanel(page, agent.config)
        self.about_panel = AboutPanel(page)
        self.unified_settings = UnifiedSettingsPanel(page, self.model_settings_panel, self.sys_settings_panel, self.task_config_panel, self.connection_panel, self.about_panel)
        self.status_sidebar = StatusSidebar(page, agent.config.paths.task_dir, agent.config.paths.token_file,
                                            extra_controls=[self.task_switch],
                                            on_chat_select=lambda p, s="": self._on_sidebar_select(p, s))
        self.status_sidebar._default_work_dir = agent.config.execution.work_dir

        # 创建 Chat 模式的 task_manager 并初始化 Chater
        self._chat_task_manager = TaskManager()
        subtask = {
            TaskField.SUB_TASK_NAME: "通用对话",
            TaskField.SUB_TASK_DETAIL: "Chat 模式通用对话",
            TaskField.TASK_TYPE: "其他",
        }
        self._chat_task_manager.set_subtask(subtask)
        self._chat_task_manager.set_subtask_project(agent.config.execution.work_dir)
        self.agent.chater._chat_init(self._chat_task_manager)

        self._setup_window()
        self._build_title_bar()
        self._assemble_page()
        self._start_poll_loop()

    def _global_keyboard(self, e: ft.KeyboardEvent):
        """全局键盘事件分发：按输入框焦点路由到对应 panel"""
        if self.task_panel._input_focused:
            self.task_panel._on_page_keyboard(e)
            return
        if self.chat_panel._input_focused:
            self.chat_panel._on_page_keyboard(e)
            return

    # ── 窗口控制 ──

    def _on_sidebar_select(self, path: str, state_file: str = ""):
        """侧边栏选中项目目录，统一用 _chat_task_manager 切换路径。"""
        if path and path != self._chat_task_manager.subtask.project_path:
            self._chat_task_manager.set_subtask_project(path)
            self.eqm.send_debug(f"切换到路径：{path}")
            self.chat_panel.update_work_dir(path)
            self.agent.chater._chat_init(self._chat_task_manager)

    def _setup_window(self):
        p = self.page
        p.window.title_bar_hidden = True; p.window.frameless = True
        p.window.bgcolor = ft.Colors.TRANSPARENT; p.window.shadow = True
        p.bgcolor = ft.Colors.TRANSPARENT
        p.title = "Agix"; p.window.width = 900; p.window.height = 600; p.padding = 0

    def _toggle_sidebar(self):
        self.status_sidebar.toggle()
        self.page.update()

    def _minimize(self, e): self.page.window.minimized = True

    def _maximize(self, e):
        self.page.window.maximized = not self.page.window.maximized
        btn = self._max_btn_ref.current
        if btn:
            btn.icon = ft.Icons.FILTER_NONE if self.page.window.maximized else ft.Icons.CROP_SQUARE
            btn.tooltip = "还原" if self.page.window.maximized else "最大化"
        self.page.update()

    def _close(self, e):
        async def _do():
            try: await self.page.window.close()
            except RuntimeError: pass  # session 已关闭时忽略
        self.page.run_task(_do)

    # ── 标题栏 ──

    def _build_lights_and_switch(self):
        self.task_light = ft.Container(width=14, height=14, border_radius=8, bgcolor=ft.Colors.BLUE, opacity=0.5)
        self.task_light.tooltip = "Task模式呼吸灯"; self.task_light.on_click = lambda e: None
        self.task_switch = ft.Switch(value=False, height=32, on_change=self.task_panel.on_switch_change, scale=0.8)
        self.task_switch.tooltip = "任务面板开关"

    def _build_title_bar(self):
        self.tb = ft.Container(content=ft.Row([
            ft.WindowDragArea(content=ft.Row([
                ft.IconButton(icon=ft.Icons.FORMAT_INDENT_DECREASE, icon_size=18, tooltip="折叠侧边栏",
                              on_click=lambda e: self._toggle_sidebar()),
                self.task_light,
                ft.Text("Agix", size=14, expand=True,text_align=ft.TextAlign.CENTER)
            ], alignment=ft.MainAxisAlignment.START), expand=True),
            ft.IconButton(icon=ft.Icons.SETTINGS, icon_size=18, tooltip="设置", on_click=lambda e: self.unified_settings.open()),
            ft.IconButton(icon=ft.Icons.MINIMIZE, icon_size=18, tooltip="最小化", on_click=self._minimize),
            ft.IconButton(icon=ft.Icons.CROP_SQUARE, icon_size=18, tooltip="最大化/还原", on_click=self._maximize, ref=self._max_btn_ref),
            ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="关闭", on_click=self._close),
        ], spacing=4), bgcolor=ft.Colors.WHITE, padding=ft.Padding(left=12, right=4, top=4, bottom=4))

    # ── 页面组装 ──

    def _assemble_page(self):
        self.page.add(ft.Container(
            content=ft.Stack([ft.Row([self.status_sidebar.container, ft.Column([ft.Container(content=self.tb.content, bgcolor=self.tb.bgcolor, padding=self.tb.padding, expand=7), ft.Container(content=self.chat_panel.container, expand=93)], expand=True)], expand=True),
                self.task_panel.wrapper, self.unified_settings.panel], expand=True),
            bgcolor=ft.Colors.WHITE,
            border_radius=ft.BorderRadius(3, 3, 3, 3),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            expand=True,
        ))

        # ── 窗口图标 ──
        logo = os.path.join(self.agent.config.paths.root, "logo.png")
        if not os.path.exists(logo):
            logo = os.path.join(self.agent.config.paths.root, "logo.ico")
        if not os.path.exists(logo):
            logo = os.path.join(os.path.expanduser("~"), ".agix", "logo.png")
        if os.path.exists(logo):
            self.page.window.icon = logo
        else:
            print(f"[WARN] logo not found at {self.agent.config.paths.root}/logo.(png|ico) or ~/.agix/logo.png")

        self.page.window.visible = True; self.page.update()
        self.chat_panel.add_greeting()
        self.status_sidebar.refresh()

    # ── 轮询 ──

    def _start_poll_loop(self):
        async def _poll():
            while True:
                chat_msgs = self.eqm.drain_display("chat")
                for m in chat_msgs:
                    t = m.get(MsgField.TYPE, ""); content = m.get(MsgField.CONTENT, ""); msg_id = m.get(MsgField.ID, "")
                    if t == MsgType.ASK_FOR_PASSWORD:
                        self.chat_panel.show_password_dialog(content, msg_id, "chat")
                        continue
                    elif t == MsgType.ASK_FOR_CONFIRMATION:
                        self.chat_panel.show_confirm_dialog(content, msg_id, "chat")
                        continue
                    self.chat_panel.add_message(m)
                task_msgs = self.eqm.drain_display("task")
                for m in task_msgs:
                    content = m.get(MsgField.CONTENT, ""); st = m.get(MsgField.STYLE, ""); t = m.get(MsgField.TYPE, "")
                    msg_id = m.get(MsgField.ID, "")
                    if t == MsgType.ASK_FOR_PASSWORD:
                        self.chat_panel.show_password_dialog(content, msg_id, "task")
                        continue
                    elif t == MsgType.ASK_FOR_CONFIRMATION:
                        self.chat_panel.show_confirm_dialog(content, msg_id, "task")
                        continue
                    if t == MsgType.TASK_NAME:
                        self.task_panel.set_task_name(content)
                        continue
                    if st == MsgStyle.STATUS or t == MsgType.STATUS:
                        self.task_panel.set_status(content)
                    elif st == MsgStyle.DEBUG or t == MsgType.DEBUG:
                        self.task_panel.add_message(content, MsgStyle.DEBUG)
                    elif st == MsgStyle.ACTION or t == MsgType.ACTION:
                        self.task_panel.add_message(content, MsgStyle.ACTION)
                    elif st == MsgStyle.THINKING or t == MsgType.THINKING:
                        self.task_panel.add_message(content, MsgStyle.THINKING)
                    else:
                        self.task_panel.add_message(content, MsgStyle.ACTION)
                self.chat_panel.set_asking(self.eqm.is_asking("chat"))
                self.status_sidebar.refresh()
                if self.eqm.is_asking("task") or len(task_msgs) > 0: self._task_ticks[0] = 4
                self.task_light.opacity = 1.0 if self._task_ticks[0] > 0 else 0.15
                if self._task_ticks[0] > 0: self._task_ticks[0] -= 1
                try: self.page.update()
                except RuntimeError: return
                await asyncio.sleep(0.3)
        self.page.run_task(_poll)


# ── Entry points ──
def build_ui(page: ft.Page, eqm: EventQueueManager, agent): AgixUI(page, eqm, agent)

def build_login_view(page: ft.Page, on_login_success, server_url="http://127.0.0.1:5000"):
    page.window.title_bar_hidden = True; page.window.frameless = True
    page.title = "Agix"; page.window.width = 720; page.window.height = 620; page.padding = 0
    def _close(e):
        async def _do(): await page.window.close()
        page.run_task(_do)
    tb = ft.Container(content=ft.Row([ft.WindowDragArea(content=ft.Text("Agix", size=14), expand=True),
        ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="关闭", on_click=_close)], spacing=0),
        bgcolor=ft.Colors.SURFACE, padding=ft.Padding(left=12, right=4, top=4, bottom=4), height=40)
    st = ft.Text("", size=13, color=ft.Colors.GREY_600)
    def _login(e):
        try:
            login_btn.disabled = True; login_btn.text = "等待浏览器登录..."; st.value = "正在打开登录页..."; page.update()
            sid = uuid.uuid4().hex[:12]
            import platform
            client_system = platform.system()
            webbrowser.open(f"{server_url}/login?session_id={sid}&client_system={client_system}")
            st.value = "已打开浏览器"; page.update()
            import urllib.request as _ur
            async def _p():
                import json as _j
                while True:
                    await asyncio.sleep(0.5)
                    try:
                        r = _ur.urlopen(f"{server_url}/api/poll_login?session_id={sid}", timeout=3)
                        d = _j.loads(r.read())
                        if d.get("token"): on_login_success(d["token"], d.get("expires_at", 0)); return
                    except Exception: pass
            page.run_task(_p)
        except Exception as ex:
            login_btn.disabled = False; login_btn.text = "手机登录"; st.value = f"错误: {ex}"; page.update()
    login_btn = ft.ElevatedButton(content=ft.Text("手机登录", size=15), on_click=_login,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6), padding=ft.Padding(20,12,20,12)))
    page.add(tb, ft.Column([ft.Container(height=40), ft.Text("Agix", size=24, weight=ft.FontWeight.W_600),
        ft.Text("AI 开发助手", size=14, color=ft.Colors.GREY_600), ft.Container(height=24), login_btn, ft.Container(height=8), st],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER))
    page.window.visible = True; page.update()
