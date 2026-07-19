"""模型设置面板 UI 组件"""

import flet as ft


class SettingsPanel:
    """模型设置面板 —— 供应商/模型选择、API Key 配置"""

    PANEL_WIDTH: int = 640
    PANEL_HEIGHT: int = 460
    PANEL_BGCOLOR = ft.Colors.WHITE
    TITLE_BGCOLOR = ft.Colors.GREY_100
    SIDEBAR_BGCOLOR = ft.Colors.BLUE_50
    DIVIDER_COLOR = ft.Colors.GREY_300
    BORDER_RADIUS: int = 10
    SHADOW = ft.BoxShadow(spread_radius=1, blur_radius=12, color=ft.Colors.BLACK26)

    LABEL_COLOR = ft.Colors.GREY_500
    TITLE_TEXT: str = "⚙ 模型设置"
    PROVIDER_LABEL: str = "供应商"
    MODEL_LABEL: str = "模型与参数"
    SAVE_LABEL: str = "保存"
    SAVE_FAIL_TITLE: str = "保存失败"
    CLOSE_TOOLTIP: str = "关闭"

    TF_DEFAULTS: dict = {"dense": True, "text_size": 13, "border_color": ft.Colors.GREY_300}

    def __init__(self, page: ft.Page, config, providers: dict, on_saved=None):
        self.page = page
        self.config = config
        self.providers = providers
        self._on_saved = on_saved

        self._provider_val = config.llm.provider
        self._model_val = config.llm.model

        # 收集各 provider 已存的 api_key
        self._provider_keys: dict = {}
        for e in config.llm_list:
            if e.get("api_key"):
                self._provider_keys[e["provider"]] = e["api_key"]
        if config.llm.provider not in self._provider_keys:
            self._provider_keys[config.llm.provider] = config.llm.api_key or ""

        self._build()

    @property
    def panel(self) -> ft.Container:
        return self._panel

    @property
    def visible(self) -> bool:
        return self._panel.visible

    def open(self):
        self._panel.visible = True
        self.page.update()

    def close(self):
        self._panel.visible = False
        self.page.update()

    # ── 构建 ──

    def _build(self):
        self._build_fields()
        self._build_panel()

    def _build_fields(self):
        cfg = self.config
        tf = self.TF_DEFAULTS
        self._s_apikey = ft.TextField(
            label="API Key", value=cfg.llm.api_key or "",
            password=True, can_reveal_password=True, hint_text="在此粘贴密钥", **tf,
        )
        self._s_base_url = ft.TextField(label="Base URL", value=cfg.llm.base_url, **tf)
        self._s_temp = ft.TextField(label="Temperature", value=str(cfg.llm.temperature), **tf)
        self._s_max_tok = ft.TextField(label="Max Tokens", value=str(cfg.llm.max_tokens), **tf)
        self._s_mem_size = ft.TextField(label="上下文窗口", value=str(cfg.llm.context_window), **tf)
        custom = "" if cfg.llm.model in self.providers.get(cfg.llm.provider, {}).get("models", []) else cfg.llm.model
        self._s_custom_model = ft.TextField(label="自定义模型", value=custom, hint_text="输入其他模型名称", **tf)

        self._plist = ft.Column([], spacing=1, scroll=ft.ScrollMode.AUTO)
        self._mlist = ft.Row([], spacing=6, wrap=True)
        self._refresh_provider_btns()
        self._refresh_model_btns()

    def _build_panel(self):
        right_top = ft.Column([
            ft.Text(self.MODEL_LABEL, weight=ft.FontWeight.W_600, size=12, color=self.LABEL_COLOR),
            self._mlist, self._s_custom_model, ft.Divider(height=1),
            self._s_temp, self._s_max_tok,
            self._s_mem_size,
            self._s_apikey, self._s_base_url,
        ], spacing=8)

        self._panel = ft.Container(
            opacity=1.0, width=self.PANEL_WIDTH, height=self.PANEL_HEIGHT,
            border_radius=ft.BorderRadius(self.BORDER_RADIUS, self.BORDER_RADIUS, self.BORDER_RADIUS, self.BORDER_RADIUS),
            bgcolor=self.PANEL_BGCOLOR,
            shadow=self.SHADOW,
            left=140, top=40, visible=False,
            content=ft.Column([
                ft.Container(content=ft.Row([
                    ft.Text(self.TITLE_TEXT, weight=ft.FontWeight.W_600, size=14),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip=self.CLOSE_TOOLTIP, on_click=lambda e: self.close()),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=ft.Padding(16, 7, 10, 7), bgcolor=self.TITLE_BGCOLOR,
                    border_radius=ft.BorderRadius(self.BORDER_RADIUS, self.BORDER_RADIUS, 0, 0),
                ),
                ft.Container(content=ft.Row([
                    ft.Container(content=ft.Column([
                        ft.Text(self.PROVIDER_LABEL, weight=ft.FontWeight.W_600, size=11, color=self.LABEL_COLOR),
                        self._plist,
                    ], spacing=4), width=130, bgcolor=self.SIDEBAR_BGCOLOR, padding=ft.Padding(8, 4, 8, 4)),
                    ft.VerticalDivider(width=1, color=self.DIVIDER_COLOR),
                    ft.Container(content=ft.Column([
                        right_top,
                        ft.Container(content=ft.Row([
                            ft.ElevatedButton(self.SAVE_LABEL, on_click=self._save, height=32),
                        ], alignment=ft.MainAxisAlignment.END), padding=ft.Padding(0, 6, 0, 0)),
                    ], spacing=4), expand=True, padding=ft.Padding(8, 4, 8, 4)),
                ], spacing=0), expand=True, padding=ft.Padding(8, 6, 8, 6)),
            ], spacing=0, expand=True),
        )

    # ── 供应商/模型切换 ──

    def _refresh_provider_btns(self):
        self._plist.controls.clear()
        for k in self.providers:
            is_active = k == self._provider_val
            self._plist.controls.append(ft.TextButton(
                self.providers[k]["name"],
                style=ft.ButtonStyle(color=ft.Colors.BLUE if is_active else ft.Colors.GREY_600, padding=ft.Padding(2, 0, 2, 0)),
                on_click=lambda e, k=k: self._click_provider(k),
            ))

    def _refresh_model_btns(self):
        self._mlist.controls.clear()
        info = self.providers.get(self._provider_val, {})
        models = info.get("models", [])
        if self._model_val not in models and models:
            self._model_val = models[0]
        for m in models:
            is_active = m == self._model_val
            self._mlist.controls.append(ft.TextButton(
                m,
                style=ft.ButtonStyle(color=ft.Colors.BLUE if is_active else ft.Colors.GREY_600, padding=ft.Padding(2, 0, 2, 0)),
                on_click=lambda e, m=m: self._click_model(m),
            ))

    def _click_model(self, m):
        self._model_val = m
        self._s_custom_model.value = m
        self._refresh_model_btns()
        self.page.update()

    def _click_provider(self, k):
        self._provider_keys[self._provider_val] = self._s_apikey.value
        self._provider_val = k
        info = self.providers.get(k, {})
        self._s_base_url.value = info.get("base_url", "")
        self._s_apikey.value = self._provider_keys.get(k, "")
        self._refresh_provider_btns()
        self._refresh_model_btns()
        self.page.update()

    # ── 保存 ──

    def _save(self, e):
        try:
            cfg = self.config
            cfg.llm.provider = self._provider_val
            cfg.llm.model = self._s_custom_model.value.strip() or self._model_val
            self._provider_keys[self._provider_val] = self._s_apikey.value.strip()
            cfg.llm.api_key = self._s_apikey.value.strip()
            cfg.llm.base_url = self._s_base_url.value.strip()
            cfg.llm.temperature = float(self._s_temp.value)
            cfg.llm.max_tokens = int(self._s_max_tok.value)
            cfg.llm.context_window = int(self._s_mem_size.value)

            existing = next(
                (e for e in cfg.llm_list if e.get("provider") == self._provider_val and e.get("model") == cfg.llm.model),
                None,
            )
            if existing:
                existing.update({
                    "api_key": cfg.llm.api_key, "base_url": cfg.llm.base_url,
                    "temperature": cfg.llm.temperature, "max_tokens": cfg.llm.max_tokens,
                    "context_window": cfg.llm.context_window,
                })
            else:
                cfg.llm_list.append({
                    "provider": self._provider_val, "model": cfg.llm.model,
                    "api_key": cfg.llm.api_key, "base_url": cfg.llm.base_url,
                    "temperature": cfg.llm.temperature, "max_tokens": cfg.llm.max_tokens,
                    "context_window": cfg.llm.context_window, "active": True, "label": "",
                })
            for e in cfg.llm_list:
                e["active"] = False
            first = next(
                (e for e in cfg.llm_list if e.get("provider") == self._provider_val and e.get("model") == cfg.llm.model),
                None,
            )
            if first:
                first["active"] = True
            cfg.save()
            self.close()
            if self._on_saved:
                self._on_saved()
        except Exception as ex:
            self.page.show_dialog(ft.AlertDialog(
                title=ft.Text(self.SAVE_FAIL_TITLE), content=ft.Text(str(ex)),
            ))
