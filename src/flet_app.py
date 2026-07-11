"""Flet UI 主模块 —— Agix 桌面界面（类封装版）"""

import asyncio, uuid, subprocess, webbrowser, flet as ft
from event_queue_manager import EventQueueManager
from meta import MsgType, MsgField, MsgStyle
from llm_client import PROVIDERS
MsgStyle.STATUS = "status"; MsgStyle.ACTION = "action"; MsgStyle.THINKING = "thinking"

_STYLE_VISUALS = {
    MsgStyle.USER:      {"bg": ft.Colors.GREEN_50},
    MsgStyle.ASSISTANT: {"bg": ft.Colors.GREY_50},
    MsgStyle.ASK:       {"bg": ft.Colors.ORANGE_50},
    MsgStyle.ERROR:     {"bg": ft.Colors.RED_50},
    MsgStyle.WARN:      {"bg": ft.Colors.AMBER_50},
    MsgStyle.STATUS:    {"bg": ft.Colors.BLUE_50},
    MsgStyle.ACTION:    {"bg": ft.Colors.TEAL_50},
    MsgStyle.THINKING:  {"bg": ft.Colors.PURPLE_50},
}

_AVATAR_DATA = {
    MsgStyle.USER:      ("👤", ft.Colors.BLUE),
    MsgStyle.ASSISTANT: ("👾", None),
    MsgStyle.ASK:       ("?",  ft.Colors.ORANGE),
    MsgStyle.ERROR:     ("!",  ft.Colors.RED),
    MsgStyle.WARN:      ("⚡", ft.Colors.AMBER),
    MsgStyle.STATUS:    ("📊", ft.Colors.BLUE),
    MsgStyle.ACTION:    ("▶",  ft.Colors.TEAL),
    MsgStyle.THINKING:  ("💭", ft.Colors.PURPLE),
}


class AgixUI:
    """Agix 桌面 UI 管理器"""
    def __init__(self, page: ft.Page, eqm: EventQueueManager, agent):
        self.page = page; self.eqm = eqm; self.agent = agent
        self._panel_pos = [420, 60]; self._drag_start = [420, 60]
        self._hover_cnt = [0]; self._chat_ticks = [0]; self._task_ticks = [0]
        self._setup_window(); self._build_title_bar()
        self._build_task_panel(); self._build_chat_panel()
        self._build_settings_panel(); self._build_system_settings_panel(); self._assemble_page()
        self._start_poll_loop()

    def _setup_window(self):
        p = self.page
        p.window.title_bar_hidden = True; p.window.frameless = True
        p.title = "Agix"; p.window.width = 900; p.window.height = 600; p.padding = 0
    def _minimize(self, e): self.page.window.minimized = True
    def _close(self, e):
        async def _do(): await self.page.window.close()
        self.page.run_task(_do)

    def _build_title_bar(self):
        self.chat_light = ft.Container(width=16, height=16, border_radius=8, bgcolor=ft.Colors.GREEN, opacity=0.15)
        self.chat_light.tooltip = "Chat"; self.chat_light.on_click = lambda e: None
        self.task_light = ft.Container(width=16, height=16, border_radius=8, bgcolor=ft.Colors.BLUE, opacity=0.15)
        self.task_light.tooltip = "Task"; self.task_light.on_click = lambda e: None
        self.task_switch = ft.Switch(value=False, height=32, on_change=self._toggle_task, scale=0.8)
        self.task_switch.tooltip = "任务面板开关"
        self.tb = ft.Container(content=ft.Row([
            self.chat_light, self.task_light, self.task_switch,
            ft.WindowDragArea(content=ft.Row([ft.Text("Agix AI Assistant", size=14)], alignment=ft.MainAxisAlignment.CENTER), expand=True),
            ft.IconButton(icon=ft.Icons.SETTINGS, icon_size=18, tooltip="模型设置", on_click=lambda e: self._open_settings()),
            ft.IconButton(icon=ft.Icons.TUNE, icon_size=18, tooltip="系统配置", on_click=lambda e: self._open_sys_settings()),
            ft.IconButton(icon=ft.Icons.MINIMIZE, icon_size=18, tooltip="最小化", on_click=self._minimize),
            ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="关闭", on_click=self._close),
        ], spacing=4), bgcolor=ft.Colors.SURFACE, padding=ft.Padding(left=12, right=4, top=4, bottom=4), height=40)

    def _build_task_panel(self):
        self.task_status_text = ft.Text("", size=12, selectable=True)
        self.task_status_list = ft.Container(content=self.task_status_text, expand=True)
        self.task_action_list = ft.ListView(expand=True, spacing=4, padding=0, auto_scroll=True)
        self.task_think_list = ft.ListView(expand=True, spacing=4, padding=0, auto_scroll=True)
        self.task_ask_input = ft.TextField(hint_text="回答 Agent...", border=ft.InputBorder.OUTLINE,
            border_color=ft.Colors.GREY_300, border_radius=6, min_lines=1, max_lines=3, expand=True, text_size=12, dense=True)
        self._task_ask_container = ft.Container(
            content=ft.Row([self.task_ask_input, ft.IconButton(icon=ft.Icons.SEND, icon_size=16, on_click=lambda e: self._task_send())], spacing=4),
            padding=ft.Padding(0, 4, 0, 0), visible=False)
        self.task_panel = ft.Container(opacity=1.0, width=640, height=400,
            border_radius=ft.BorderRadius(10, 10, 10, 10), bgcolor=ft.Colors.WHITE,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=12, color=ft.Colors.BLACK26),
            content=ft.Column([
                ft.GestureDetector(content=ft.Container(
                    content=ft.Row([ft.Text("📋 任务", weight=ft.FontWeight.W_600, size=13),
                        ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, on_click=lambda e: self._close_task_panel()),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.Padding(12, 8, 8, 8), bgcolor=ft.Colors.GREY_100, border_radius=ft.BorderRadius(10, 10, 0, 0)),
                    on_pan_start=self._on_drag_start, on_pan_update=self._on_drag_task_panel, on_enter=self._panel_enter, on_exit=self._panel_exit),
                ft.Container(content=ft.Row([
                    ft.Container(content=ft.Column([ft.Text("进度", size=10, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_600),
                        ft.Container(content=self.task_status_list, expand=True)], spacing=2),
                        width=150, padding=ft.Padding(6, 0, 6, 0), bgcolor=ft.Colors.BLUE_50, clip_behavior=ft.ClipBehavior.HARD_EDGE),
                    ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                    ft.Container(content=ft.Column([
                        ft.Column([ft.Text("步骤", size=10, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_600),
                            ft.Container(content=self.task_action_list, expand=True)], spacing=2, expand=2),
                        ft.Divider(height=1, color=ft.Colors.GREY_300),
                        ft.Column([ft.Text("思考", size=10, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_600),
                            ft.Container(content=self.task_think_list, expand=True)], spacing=2, expand=3),
                        ft.Divider(height=1, color=ft.Colors.ORANGE_200), self._task_ask_container],
                        spacing=0), expand=True, padding=ft.Padding(6, 0, 6, 0), clip_behavior=ft.ClipBehavior.HARD_EDGE),
                ], spacing=0), expand=True, padding=ft.Padding(6, 4, 6, 6)),
            ], spacing=0, expand=True))
        self._task_panel_wrapper = ft.GestureDetector(content=self.task_panel, on_enter=self._panel_enter, on_exit=self._panel_exit)
        self._task_panel_wrapper.left = self._panel_pos[0]; self._task_panel_wrapper.top = self._panel_pos[1]
        self._task_panel_wrapper.visible = False

    def _on_drag_start(self, e): self._drag_start[0] = self._panel_pos[0]; self._drag_start[1] = self._panel_pos[1]
    def _on_drag_task_panel(self, e: ft.DragUpdateEvent):
        self._panel_pos[0] = self._drag_start[0] + e.global_delta.x; self._panel_pos[1] = self._drag_start[1] + e.global_delta.y
        self._panel_pos[0] = max(0, min(self._panel_pos[0], self.page.window.width - 640))
        self._panel_pos[1] = max(0, min(self._panel_pos[1], self.page.window.height - 400))
        self._task_panel_wrapper.left = self._panel_pos[0]; self._task_panel_wrapper.top = self._panel_pos[1]; self.page.update()
    def _panel_enter(self, e): self._hover_cnt[0] += 1; self.task_panel.opacity = 1.0; self.page.update()
    def _panel_exit(self, e):
        self._hover_cnt[0] = max(0, self._hover_cnt[0] - 1)
        if self._hover_cnt[0] == 0: self.task_panel.opacity = 0.3; self.page.update()
    def _close_task_panel(self):
        self.task_switch.value = False; self._task_panel_wrapper.visible = False
        self._hover_cnt[0] = 0; self.task_panel.opacity = 0.3; self.page.update()
    def _toggle_task(self, e):
        self._task_panel_wrapper.visible = self.task_switch.value
        if self.task_switch.value: self.task_panel.opacity = 0.3; self.page.update()
    def _task_send(self):
        t = self.task_ask_input.value.strip()
        if not t: return
        self.task_action_list.controls.append(_task_msg(t, style=MsgStyle.USER))
        self.eqm.respond_to_ask(t, msg_id=self.eqm.get_pending_ask_id("task"), mode="task")
        self.task_ask_input.value = ""; self.page.update()

    def _build_chat_panel(self):
        self.cl = ft.ListView(expand=True, spacing=8, padding=15, auto_scroll=True)
        self.ca = ft.Text("", size=12, color=ft.Colors.ORANGE, visible=False)
        self.ci = ft.TextField(hint_text="输入消息...", border=ft.InputBorder.OUTLINE,
            border_color=ft.Colors.GREY_300, focused_border_color=ft.Colors.GREY_400,
            border_radius=10, min_lines=1, max_lines=5, expand=True, text_size=14)
        self.ci.on_submit = lambda e: self._send()

        def _open_work_dir(e): subprocess.Popen(['xdg-open', self.agent.work_dir])

        def _get_active_label():
            for e in self.agent.config.llm_list:
                if e.get("active") and e.get("api_key"):
                    return e.get("label") or f"{e.get('provider','')}/{e.get('model','')}"
            return "未配置"

        def _switch_to_model(idx):
            self.agent.config.switch_llm(idx)
            self.agent.config.save()
            self.agent.chat_llm.model = self.agent.config.llm.model
            self.agent.chat_llm.api_key = self.agent.config.llm.api_key
            self.agent.task_llm.model = self.agent.config.llm.model
            self.agent.task_llm.api_key = self.agent.config.llm.api_key
            print(f"debug: switched model → {self.agent.config.llm.model}")
            self._model_label.value = _get_active_label()
            self.page.update()

        self._model_label = ft.Text(_get_active_label(), size=13, color=ft.Colors.GREY_500)

        sb_ctrl = ft.Container(content=ft.Row([
            ft.Row([ft.Text(f"当前工作目录：{self.agent.work_dir}", size=13, color=ft.Colors.GREY_500, overflow=ft.TextOverflow.ELLIPSIS),
                ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, icon_size=14, tooltip="打开工作目录", on_click=_open_work_dir)], spacing=4),
            ft.Row([self._model_label,
                ft.PopupMenuButton(
                    icon=ft.Icons.SWAP_HORIZ, icon_size=14,
                    tooltip="切换模型",
                    items=[
                        ft.PopupMenuItem(
                            content=(e.get("label") or f"{e.get('provider','')}/{e.get('model','')}")
                                + ("" if e.get("api_key") else " (未配置)"),
                            on_click=lambda e, i=idx: _switch_to_model(i),
                            disabled=not e.get("api_key"),
                        )
                        for idx, e in enumerate(self.agent.config.llm_list)
                    ],
                ),
            ], spacing=4),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=ft.Colors.GREY_50, height=32, padding=ft.Padding(left=8, right=8, top=4, bottom=4))

        self.cp = ft.Column([ft.Container(content=self.cl, expand=True), ft.Divider(height=1),
            ft.Row([self.ca], alignment=ft.MainAxisAlignment.START),
            ft.Container(content=ft.Row([self.ci,
                ft.IconButton(icon=ft.Icons.SEND, on_click=lambda e: self._send(), icon_size=20),
                ft.IconButton(icon=ft.Icons.STOP, on_click=lambda e: self.eqm.request_cancel("chat"), icon_size=20, tooltip="停止执行"),
            ]), padding=ft.Padding(left=10, right=10, top=6, bottom=4)),
            sb_ctrl], expand=True)

    def _send(self):
        t = self.ci.value.strip()
        if not t: return
        if self.eqm.is_asking("chat"):
            self.cl.controls.append(_r(_msg(t, is_user=True)))
            self.eqm.respond_to_ask(t, msg_id=self.eqm.get_pending_ask_id("chat"), mode="chat")
        else:
            self.cl.controls.append(_r(_msg(t, is_user=True)))
            self.eqm.send_user_input(t, mode="chat")
        self.ci.value = ""
        self.page.update()
        async def _refocus():
            await self.ci.focus()
            self.page.update()
        self.page.run_task(_refocus)

    def _build_settings_panel(self):
        cfg = self.agent.config; self._s_provider_val = cfg.llm.provider; self._s_model_val = cfg.llm.model
        _provider_keys = {}
        for e in cfg.llm_list:
            if e.get("api_key"):
                _provider_keys[e["provider"]] = e["api_key"]
        if cfg.llm.provider not in _provider_keys:
            _provider_keys[cfg.llm.provider] = cfg.llm.api_key or ""

        def _refresh_provider_btns():
            _plist.controls.clear()
            for k in PROVIDERS:
                is_active = k == self._s_provider_val
                _plist.controls.append(ft.TextButton(PROVIDERS[k]["name"],
                    style=ft.ButtonStyle(color=ft.Colors.BLUE if is_active else ft.Colors.GREY_600, padding=ft.Padding(2,0,2,0)),
                    on_click=lambda e, k=k: _click_provider(k)))

        def _refresh_model_btns():
            _mlist.controls.clear()
            info = PROVIDERS.get(self._s_provider_val, {}); models = info.get("models", [])
            if self._s_model_val not in models and models: self._s_model_val = models[0]
            for m in models:
                is_active = m == self._s_model_val
                _mlist.controls.append(ft.TextButton(m,
                    style=ft.ButtonStyle(color=ft.Colors.BLUE if is_active else ft.Colors.GREY_600, padding=ft.Padding(2,0,2,0)),
                    on_click=lambda e, m=m: _click_model(m)))

        def _click_model(m): self._s_model_val = m; _refresh_model_btns(); self.page.update()

        def _click_provider(k):
            _provider_keys[self._s_provider_val] = self._s_apikey.value
            self._s_provider_val = k
            info = PROVIDERS.get(k, {}); self._s_base_url.value = info.get("base_url", "")
            self._s_apikey.value = _provider_keys.get(k, "")
            _refresh_provider_btns(); _refresh_model_btns(); self.page.update()

        _plist = ft.Column([], spacing=1, scroll=ft.ScrollMode.AUTO); _mlist = ft.Row([], spacing=6, wrap=True)
        _refresh_provider_btns(); _refresh_model_btns()

        tf = {"dense": True, "text_size": 13, "border_color": ft.Colors.GREY_300}
        self._s_apikey = ft.TextField(label="API Key", value=cfg.llm.api_key or "", password=True, can_reveal_password=True, hint_text="在此粘贴密钥", **tf)
        self._s_base_url = ft.TextField(label="Base URL", value=cfg.llm.base_url, **tf)
        self._s_temp = ft.TextField(label="Temperature", value=str(cfg.llm.temperature), **tf)
        self._s_max_tok = ft.TextField(label="Max Tokens", value=str(cfg.llm.max_tokens), **tf)
        self._s_rounds = ft.TextField(label="对话轮数上限", value=str(cfg.llm.llm_max_allowed_rounds), **tf)
        self._s_mem_en = ft.Switch(label="启用记忆", value=cfg.llm.memory_enabled)
        self._s_mem_size = ft.TextField(label="记忆条数", value=str(cfg.llm.memory_size), **tf)
        self._s_custom_model = ft.TextField(label="自定义模型", value="" if cfg.llm.model in PROVIDERS.get(cfg.llm.provider, {}).get("models", []) else cfg.llm.model, hint_text="输入其他模型名称", **tf)

        right_top = ft.Column([ft.Text("模型与参数", weight=ft.FontWeight.W_600, size=12, color=ft.Colors.GREY_700),
            _mlist, self._s_custom_model, ft.Divider(height=1),
            self._s_temp, self._s_max_tok, self._s_rounds,
            ft.Row([self._s_mem_size, self._s_mem_en], spacing=8)], spacing=8, scroll=ft.ScrollMode.AUTO)
        right_bot = ft.Column([ft.Text("密钥配置", weight=ft.FontWeight.W_600, size=12, color=ft.Colors.GREY_700),
            self._s_apikey, self._s_base_url], spacing=8)

        def _save_settings(e):
            try:
                cfg.llm.provider = self._s_provider_val
                cfg.llm.model = self._s_custom_model.value.strip() or self._s_model_val
                _provider_keys[self._s_provider_val] = self._s_apikey.value.strip()
                cfg.llm.api_key = self._s_apikey.value.strip()
                cfg.llm.base_url = self._s_base_url.value.strip()
                cfg.llm.temperature = float(self._s_temp.value)
                cfg.llm.max_tokens = int(self._s_max_tok.value)
                cfg.llm.llm_max_allowed_rounds = int(self._s_rounds.value)
                cfg.llm.memory_enabled = self._s_mem_en.value
                cfg.llm.memory_size = int(self._s_mem_size.value)
                # Upsert entry: match by provider+model, not just provider
                existing = next((e for e in cfg.llm_list if e.get("provider") == self._s_provider_val and e.get("model") == cfg.llm.model), None)
                if existing:
                    existing.update({"api_key": cfg.llm.api_key, "base_url": cfg.llm.base_url,
                        "temperature": cfg.llm.temperature, "max_tokens": cfg.llm.max_tokens,
                        "llm_max_allowed_rounds": cfg.llm.llm_max_allowed_rounds,
                        "memory_enabled": cfg.llm.memory_enabled, "memory_size": cfg.llm.memory_size})
                else:
                    cfg.llm_list.append({"provider": self._s_provider_val, "model": cfg.llm.model, "api_key": cfg.llm.api_key,
                        "base_url": cfg.llm.base_url, "temperature": cfg.llm.temperature, "max_tokens": cfg.llm.max_tokens,
                        "llm_max_allowed_rounds": cfg.llm.llm_max_allowed_rounds, "memory_enabled": cfg.llm.memory_enabled,
                        "memory_size": cfg.llm.memory_size, "active": True, "label": ""})
                for e in cfg.llm_list: e["active"] = False
                first = next((e for e in cfg.llm_list if e.get("provider") == self._s_provider_val and e.get("model") == cfg.llm.model), None)
                if first: first["active"] = True
                cfg.save()
                self._settings_panel.visible = False; self.page.update()
                print(f"debug: settings saved — {cfg.llm.provider}/{cfg.llm.model}")
            except Exception as ex:
                self.page.show_dialog(ft.AlertDialog(title=ft.Text("保存失败"), content=ft.Text(str(ex))))

        self._settings_panel = ft.Container(opacity=1.0, width=640, height=520,
            border_radius=ft.BorderRadius(10,10,10,10), bgcolor=ft.Colors.WHITE,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=12, color=ft.Colors.BLACK26),
            left=140, top=40, visible=False,
            content=ft.Column([
                ft.Container(content=ft.Row([ft.Text("⚙ 模型设置", weight=ft.FontWeight.W_600, size=14),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, on_click=lambda e: self._close_settings()),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=ft.Padding(16,10,10,10), bgcolor=ft.Colors.GREY_100, border_radius=ft.BorderRadius(10,10,0,0)),
                ft.Container(content=ft.Row([
                    ft.Container(content=ft.Column([ft.Text("供应商", weight=ft.FontWeight.W_600, size=11, color=ft.Colors.GREY_500),
                        _plist], spacing=4), width=130, bgcolor=ft.Colors.BLUE_50, padding=ft.Padding(8,4,8,4)),
                    ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                    ft.Container(content=ft.Column([right_top, ft.Divider(height=1, color=ft.Colors.GREY_300), right_bot,
                        ft.Container(content=ft.Row([ft.ElevatedButton("保存", on_click=_save_settings, height=32)], alignment=ft.MainAxisAlignment.END), padding=ft.Padding(0,6,0,0)),
                    ], spacing=4), expand=True, padding=ft.Padding(8,4,8,4)),
                ], spacing=0), expand=True, padding=ft.Padding(8,6,8,6)),
            ], spacing=0, expand=True))

    def _open_settings(self): self._settings_panel.visible = True; self.page.update()
    def _close_settings(self): self._settings_panel.visible = False; self.page.update()

    def _build_system_settings_panel(self):
        cfg = self.agent.config
        tf = {"dense": True, "text_size": 13, "border_color": ft.Colors.GREY_300}
        self._sys_timeout = ft.TextField(label="超时(秒)", value=str(cfg.execution.timeout), width=100, **tf)
        self._sys_work_dir = ft.TextField(value=cfg.execution.work_dir, read_only=True, **tf)
        self._sys_enable_history = ft.Switch(label="启用历史关联", value=cfg.execution.enable_history_association)

        self._sys_log_terminal = ft.Switch(label="输出到终端", value=cfg.log.log_to_terminal)
        self._sys_log_file = ft.Switch(label="写入文件", value=cfg.log.log_to_file)
        self._sys_log_history = ft.Switch(label="记录历史", value=cfg.log.history)
        self._sys_auth_interactive = ft.Switch(label="交互模式", value=cfg.auth.interactive)
        self._sys_auth_sensitive = ft.Switch(label="敏感命令检查", value=cfg.auth.sensitive_command_check)

        def _save_sys(e):
            try:
                cfg.execution.timeout = int(self._sys_timeout.value)
                cfg.execution.work_dir = self._sys_work_dir.value.strip()
                cfg.execution.enable_history_association = self._sys_enable_history.value
                cfg.log.log_to_terminal = self._sys_log_terminal.value
                cfg.log.log_to_file = self._sys_log_file.value
                cfg.log.history = self._sys_log_history.value
                cfg.auth.interactive = self._sys_auth_interactive.value
                cfg.auth.sensitive_command_check = self._sys_auth_sensitive.value
                cfg.save()
                self._sys_settings_panel.visible = False
                self.page.update()
            except Exception as ex:
                self.page.show_dialog(ft.AlertDialog(title=ft.Text("保存失败"), content=ft.Text(str(ex))))

        self._sys_settings_panel = ft.Container(opacity=1.0, width=480, height=420,
            border_radius=ft.BorderRadius(10,10,10,10), bgcolor=ft.Colors.WHITE,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=12, color=ft.Colors.BLACK26),
            left=180, top=60, visible=False,
            content=ft.Column([
                ft.Container(content=ft.Row([ft.Text("🔧 系统配置", weight=ft.FontWeight.W_600, size=14),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, on_click=lambda e: self._close_sys_settings()),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=ft.Padding(16,10,10,10), bgcolor=ft.Colors.GREY_100, border_radius=ft.BorderRadius(10,10,0,0)),
                ft.Container(content=ft.Column([
                    ft.Text("执行", weight=ft.FontWeight.W_600, size=12, color=ft.Colors.GREY_700),
                    ft.Row([self._sys_timeout, self._sys_enable_history], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([self._sys_work_dir, ft.IconButton(icon=ft.Icons.FOLDER_OPEN, icon_size=18, tooltip="选择目录", on_click=lambda e: self._pick_dir())], spacing=4),
                    ft.Divider(height=1),
                    ft.Text("日志", weight=ft.FontWeight.W_600, size=12, color=ft.Colors.GREY_700),
                    ft.Row([self._sys_log_terminal, self._sys_log_file, self._sys_log_history], spacing=16, wrap=True),
                    ft.Divider(height=1),
                    ft.Text("安全", weight=ft.FontWeight.W_600, size=12, color=ft.Colors.GREY_700),
                    ft.Row([self._sys_auth_interactive, self._sys_auth_sensitive], spacing=16, wrap=True),
                    ft.Container(content=ft.Row([ft.ElevatedButton("保存", on_click=_save_sys, height=32)], alignment=ft.MainAxisAlignment.END), padding=ft.Padding(0,6,0,0)),
                ], spacing=8), expand=True, padding=ft.Padding(16,12,16,12)),
            ], spacing=0, expand=True))

    def _open_sys_settings(self): self._sys_settings_panel.visible = True; self.page.update()
    def _close_sys_settings(self): self._sys_settings_panel.visible = False; self.page.update()

    def _pick_dir(self):
        r = subprocess.run(
            ["zenity", "--file-selection", "--directory", "--title=选择工作目录"],
            capture_output=True, text=True)
        path = r.stdout.strip()
        if path:
            self._sys_work_dir.value = path
            self.page.update()

    def _assemble_page(self):
        self.page.add(ft.Stack([ft.Column([self.tb, self.cp], expand=True), self._task_panel_wrapper, self._settings_panel, self._sys_settings_panel], expand=True))
        self.page.window.visible = True; self.page.update()
        self.cl.controls.append(_msg("你好！我是 Agix，你的 AI 开发助手。\n我可以帮你写代码、管理任务、回答问题。"))
        self.page.window.icon = "/home/agent_native/logo.ico"; self.page.update()

    def _start_poll_loop(self):
        async def _poll():
            while True:
                chat_msgs = self.eqm.drain_display("chat")
                for m in chat_msgs: _al(self.cl, m)
                task_msgs = self.eqm.drain_display("task")
                for m in task_msgs:
                    content = m.get(MsgField.CONTENT, ""); st = m.get(MsgField.STYLE, ""); t = m.get(MsgField.TYPE, "")
                    if st == MsgStyle.STATUS or t == MsgType.STATUS: self.task_status_text.value = content
                    elif st == MsgStyle.ACTION or t == MsgType.ACTION: self.task_action_list.controls.append(_task_msg(content, style=MsgStyle.ACTION))
                    elif st == MsgStyle.THINKING or t == MsgType.THINKING: self.task_think_list.controls.append(_task_msg(content, style=MsgStyle.THINKING))
                    else: self.task_action_list.controls.append(_task_msg(content, style=MsgStyle.ACTION))
                self.ca.visible = self.eqm.is_asking("chat")
                if self.eqm.is_asking("chat") or len(chat_msgs) > 0: self._chat_ticks[0] = 4
                if self.eqm.is_asking("task") or len(task_msgs) > 0: self._task_ticks[0] = 4
                self.chat_light.opacity = 1.0 if self._chat_ticks[0] > 0 else 0.15
                self.task_light.opacity = 1.0 if self._task_ticks[0] > 0 else 0.15
                if self._chat_ticks[0] > 0: self._chat_ticks[0] -= 1
                if self._task_ticks[0] > 0: self._task_ticks[0] -= 1
                self._task_ask_container.visible = self.eqm.is_asking("task")
                try: self.page.update()
                except RuntimeError: return
                await asyncio.sleep(0.3)
        self.page.run_task(_poll)


# ── Helper functions ──
def _r(w): return ft.Row([w], alignment=ft.MainAxisAlignment.END)
def _avatar(style_type: str) -> ft.Container:
    char, color = _AVATAR_DATA.get(style_type, ("?", ft.Colors.GREY))
    text_color = ft.Colors.GREEN if color is None else ft.Colors.WHITE
    return ft.Container(content=ft.Text(char, size=18, color=text_color, text_align=ft.TextAlign.CENTER), width=32, height=32, border_radius=16, bgcolor=color)
def _msg(text, is_user=False, is_ask=False, style=""):
    style_type = MsgStyle.ASSISTANT
    if is_user: style_type = MsgStyle.USER
    elif is_ask: style_type = MsgStyle.ASK
    elif style in _STYLE_VISUALS: style_type = style
    v = _STYLE_VISUALS[style_type]; avatar = _avatar(style_type)
    bubble = ft.Container(content=ft.Text(text, size=14, selectable=True), bgcolor=v["bg"], border_radius=10, padding=ft.Padding(left=14, right=14, top=10, bottom=10))
    if is_user: return ft.Row([bubble, avatar], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.END)
    return ft.Row([avatar, bubble], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.START)
def _task_msg(text, style):
    v = _STYLE_VISUALS.get(style, _STYLE_VISUALS[MsgStyle.ASSISTANT])
    return ft.Container(content=ft.Text(text, size=12, selectable=True), bgcolor=v["bg"], border_radius=6, clip_behavior=ft.ClipBehavior.HARD_EDGE, padding=ft.Padding(left=8, right=8, top=4, bottom=4))
def _al(lst, msg, is_user=False):
    is_ask = msg.get(MsgField.TYPE) == MsgType.ASK
    lst.controls.append(_msg(msg.get(MsgField.CONTENT, ""), is_user=is_user, is_ask=is_ask, style=msg.get(MsgField.STYLE, "")))
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
            sid = uuid.uuid4().hex[:12]; webbrowser.open(f"{server_url}/login?session_id={sid}")
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
