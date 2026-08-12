"""模型设置面板 UI 组件"""

import flet as ft


class ModelSettingsPanel:
    """模型设置面板 —— 供应商/模型选择、API Key 配置"""

    PANEL_WIDTH: int = 700
    PANEL_HEIGHT: int = 460
    PANEL_BGCOLOR = ft.Colors.WHITE
    TITLE_BGCOLOR = ft.Colors.GREY_100
    SIDEBAR_BGCOLOR = ft.Colors.WHITE
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
    _UNSAVED: str = "● 未保存(保存后重启生效)"

    def __init__(self, page: ft.Page, config, providers: dict, on_saved=None):
        self._dirty = False
        self._unsaved_badge = ft.Text("", size=11, color=ft.Colors.ORANGE_600)
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
    def content_body(self) -> ft.Row:
        return self._content_body

    @property
    def visible(self) -> bool:
        return self._panel.visible

    def open(self):
        self._panel.visible = True
        self.page.update()

    def close(self):
        self._confirm_close()

    def _confirm_close(self):
        if not self._dirty:
            self._do_close()
            return
        def on_confirm(ev):
            self._close_dlg(dlg)
            self._dirty = False
            self._do_close()
        dlg = ft.AlertDialog(
            bgcolor=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=6),
            content_padding=ft.Padding(16, 16, 16, 16),
            title=ft.Text("未保存的修改"),
            content=ft.Text("当前有未保存的修改，关闭将丢失这些更改。确定要放弃修改吗？"),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dlg(dlg)),
                ft.TextButton("放弃修改", on_click=on_confirm,
                              style=ft.ButtonStyle(color=ft.Colors.RED)),
            ],
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    def _do_close(self):
        self._panel.visible = False
        self.page.update()

    def _mark_dirty(self):
        self._dirty = True
        self._s_custom_model.error = None
        self._s_apikey.error = None
        self._s_base_url.error = None
        self._s_temp.error = None
        self._s_max_tok.error = None
        self._s_mem_size.error = None
        self._unsaved_badge.value = self._UNSAVED
        self.page.update()

    # ── 构建 ──

    def _build(self):
        self._build_fields()
        self._build_panel()

    def _build_fields(self):
        cfg = self.config
        tf = self.TF_DEFAULTS

        self._s_custom_model = ft.TextField(
            label="模型名称", value=cfg.llm.model, hint_text="输入模型名称", on_change=lambda e: self._mark_dirty(), **tf,
        )

        self._s_apikey = ft.TextField(
            label="API Key", value=cfg.llm.api_key or "", on_change=lambda e: self._mark_dirty(),
            password=True, can_reveal_password=True, hint_text="在此粘贴密钥", **tf,
        )
        self._s_base_url = ft.TextField(label="Base URL", value=cfg.llm.base_url, on_change=lambda e: self._mark_dirty(), **tf)
        self._s_temp = ft.TextField(label="Temperature", value=str(cfg.llm.temperature), on_change=lambda e: self._mark_dirty(), **tf)
        self._s_max_tok = ft.TextField(label="Max Tokens", value=str(cfg.llm.max_tokens), on_change=lambda e: self._mark_dirty(), **tf)
        self._s_mem_size = ft.TextField(label="上下文窗口", value=str(cfg.llm.context_window), on_change=lambda e: self._mark_dirty(), **tf)
        self._s_vision = ft.Switch(
            label="支持图片输入（多模态）",
            value=bool(cfg.llm.supports_vision),
            on_change=lambda e: self._mark_dirty(),
        )
        self._model_chips = ft.Row([], wrap=True, spacing=4)

        self._plist = ft.Column([], spacing=1, scroll=ft.ScrollMode.AUTO)
        self._refresh_provider_btns()
        self._refresh_model_chips(self._provider_val)

    def _build_panel(self):
        right_top = ft.Column([
            self._model_chips,
            self._s_custom_model,
            self._s_base_url,
            self._s_apikey,
            self._s_temp, self._s_max_tok, self._s_mem_size,
            self._s_vision,
        ], spacing=20)

        self._content_body = ft.Row([
            ft.Container(content=ft.Column([
                self._plist,
            ], spacing=4), width=130, bgcolor=self.SIDEBAR_BGCOLOR, padding=ft.Padding(8, 4, 8, 4)),
            ft.Container(content=ft.Column([
                right_top,
                ft.Container(expand=True),
                ft.Container(content=ft.Row([
                    self._unsaved_badge,
                    ft.ElevatedButton(self.SAVE_LABEL, on_click=self._save, height=32),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), padding=ft.Padding(0, 6, 0, 0)),
            ], spacing=4), expand=True, padding=ft.Padding(8, 4, 8, 4)),
        ], spacing=0)

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
                ft.Container(content=self._content_body, expand=True, padding=ft.Padding(8, 6, 8, 6)),
            ], spacing=0, expand=True),
        )

    # ── 供应商切换 ──

    def _refresh_provider_btns(self):
        self._plist.controls.clear()
        seen = set()
        for entry in self.config.llm_list:
            provider = entry.get("provider")
            if provider and provider not in seen:
                seen.add(provider)
                is_active = provider == self._provider_val
                name = self.providers.get(provider, {}).get("name", provider)
                self._plist.controls.append(ft.Row([
                    ft.TextButton(
                        name, data=provider,
                        style=ft.ButtonStyle(color=ft.Colors.BLUE if is_active else ft.Colors.GREY_600, padding=ft.Padding(2, 0, 2, 0)),
                        on_click=lambda e, k=provider: self._click_provider(k),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.REMOVE, icon_size=14,
                        tooltip=f"删除 {name}",
                        on_click=lambda e, k=provider: self._delete_provider(k),
                        style=ft.ButtonStyle(color=ft.Colors.GREY_400),
                    ),
                ], spacing=0, alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
        # 若当前选中的供应商不在 llm_list 中（刚刚通过 + 添加的），也显示
        if self._provider_val and self._provider_val not in seen:
            self._plist.controls.append(ft.Row([
                ft.TextButton(
                    self._provider_val, data=self._provider_val,
                    style=ft.ButtonStyle(color=ft.Colors.BLUE, padding=ft.Padding(2, 0, 2, 0)),
                    on_click=lambda e, k=self._provider_val: self._click_provider(k),
                ),
                ft.IconButton(
                    icon=ft.Icons.REMOVE, icon_size=14,
                    on_click=lambda e, k=self._provider_val: self._delete_provider(k),
                    style=ft.ButtonStyle(color=ft.Colors.GREY_400),
                ),
            ], spacing=0, alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
        # "+" 按钮
        self._plist.controls.append(ft.IconButton(
            icon=ft.Icons.ADD, icon_size=18,
            tooltip="添加供应商",
            on_click=self._add_provider,
            style=ft.ButtonStyle(color=ft.Colors.GREY_400),
        ))

    def _click_provider(self, k):
        self._provider_keys[self._provider_val] = self._s_apikey.value
        self._provider_val = k
        info = self.providers.get(k, {})
        # 从 llm_list 加载该供应商已有配置
        found = None
        for entry in self.config.llm_list:
            if entry.get("provider") == k:
                found = entry
                break
        if found and found.get("model"):
            self._s_custom_model.value = found.get("model", "")
            self._s_base_url.value = found.get("base_url", "") or info.get("base_url", "")
            self._s_apikey.value = self._provider_keys.get(k, found.get("api_key", ""))
            self._s_temp.value = str(found.get("temperature", 0.7))
            self._s_max_tok.value = str(found.get("max_tokens", 10240))
            self._s_mem_size.value = str(found.get("context_window", 80))
            self._s_vision.value = bool(found.get("supports_vision", False))
        else:
            self._s_custom_model.value = ""
            self._s_base_url.value = info.get("base_url", "")
            self._s_apikey.value = self._provider_keys.get(k, "")
            self._s_temp.value = "0.7"
            self._s_max_tok.value = "10240"
            self._s_mem_size.value = "80"
            self._s_vision.value = False
        self._refresh_provider_btns()
        self._refresh_model_chips(k)
        self._mark_dirty()
        self.page.update()

    # ── 添加供应商 ──

    def _add_provider(self, e):
        def on_ok(ev):
            name = name_field.value.strip()
            if not name:
                name_field.error = "名称不能为空"
                name_field.update()
                return
            self._close_dlg(dlg)
            # 保存当前表单值
            self._provider_keys[self._provider_val] = self._s_apikey.value
            # 切换到新供应商
            self._provider_val = name
            info = self.providers.get(name, {})
            self._s_custom_model.value = ""
            self._s_base_url.value = info.get("base_url", "")
            self._s_apikey.value = self._provider_keys.get(name, "")
            self._s_temp.value = "0.7"
            self._s_max_tok.value = "10240"
            self._s_mem_size.value = "80"
            self._s_vision.value = False
            self._refresh_provider_btns()
            self._refresh_model_chips(name)
            self._mark_dirty()
            self.page.update()

        name_field = ft.TextField(label="供应商名称", hint_text="输入新供应商名称", dense=True)
        dlg = ft.AlertDialog(
            bgcolor=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=6),
            content_padding=ft.Padding(16, 16, 16, 16),
            title=ft.Text("添加供应商"),
            content=name_field,
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dlg(dlg)),
                ft.TextButton("确定", on_click=on_ok),
            ],
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()
    
    def _close_dlg(self, dlg):
        dlg.open = False
        self.page.update()

    # ── 保存 ──

    def _save(self, e):
        try:
            # 必填校验
            has_err = False
            if not self._s_custom_model.value.strip():
                self._s_custom_model.error = "模型名称不能为空"
                has_err = True
            else:
                self._s_custom_model.error = None
            if not self._s_apikey.value.strip():
                self._s_apikey.error = "API Key 不能为空"
                has_err = True
            else:
                self._s_apikey.error = None
            if not self._s_base_url.value.strip():
                self._s_base_url.error = "Base URL 不能为空"
                has_err = True
            else:
                self._s_base_url.error = None
            if not self._s_temp.value.strip():
                self._s_temp.error = "不能为空"
                has_err = True
            else:
                self._s_temp.error = None
            if not self._s_max_tok.value.strip():
                self._s_max_tok.error = "不能为空"
                has_err = True
            else:
                self._s_max_tok.error = None
            if not self._s_mem_size.value.strip():
                self._s_mem_size.error = "不能为空"
                has_err = True
            else:
                self._s_mem_size.error = None
            if has_err:
                self.page.update()
                return
            cfg = self.config
            cfg.llm.provider = self._provider_val
            cfg.llm.model = self._s_custom_model.value.strip()
            self._provider_keys[self._provider_val] = self._s_apikey.value.strip()
            cfg.llm.api_key = self._s_apikey.value.strip()
            cfg.llm.base_url = self._s_base_url.value.strip()
            cfg.llm.temperature = float(self._s_temp.value)
            cfg.llm.max_tokens = int(self._s_max_tok.value)
            cfg.llm.context_window = int(self._s_mem_size.value)
            cfg.llm.supports_vision = self._s_vision.value

            existing = next(
                (e for e in cfg.llm_list if e.get("provider") == self._provider_val and e.get("model") == cfg.llm.model),
                None,
            )
            if existing:
                existing.update({
                    "api_key": cfg.llm.api_key, "base_url": cfg.llm.base_url,
                    "temperature": cfg.llm.temperature, "max_tokens": cfg.llm.max_tokens,
                    "context_window": cfg.llm.context_window,
                    "supports_vision": cfg.llm.supports_vision,
                })
            else:
                cfg.llm_list.append({
                    "provider": self._provider_val, "model": cfg.llm.model,
                    "api_key": cfg.llm.api_key, "base_url": cfg.llm.base_url,
                    "temperature": cfg.llm.temperature, "max_tokens": cfg.llm.max_tokens,
                    "context_window": cfg.llm.context_window, "active": True, "label": "",
                    "supports_vision": cfg.llm.supports_vision,
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
            self._dirty = False
            self._unsaved_badge.value = ""
            self.close()
            if self._on_saved:
                self._on_saved()
        except Exception as ex:
            self.page.show_dialog(ft.AlertDialog(bgcolor=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=6), content_padding=ft.Padding(16, 16, 16, 16),
                title=ft.Text(self.SAVE_FAIL_TITLE), content=ft.Text(str(ex)),
            ))

    # ── 删除供应商 ──

    def _delete_provider(self, provider):
        def on_confirm(ev):
            self._close_dlg(dlg)
            self.config.llm_list = [e for e in self.config.llm_list if e.get("provider") != provider]
            self.config.save()
            if self._provider_val == provider:
                if self.config.llm_list:
                    first = self.config.llm_list[0]
                    self._click_provider(first.get("provider"))
                else:
                    self._provider_val = ""
                    self._s_custom_model.value = ""
                    self._s_base_url.value = ""
                    self._s_apikey.value = ""
                    self._refresh_provider_btns()
                    self._refresh_model_chips("")
            else:
                self._refresh_provider_btns()
            self.page.update()
            self._mark_dirty()

        dlg = ft.AlertDialog(
            bgcolor=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=6),
            content_padding=ft.Padding(16, 16, 16, 16),
            title=ft.Text("确认删除"),
            content=ft.Text(f"确定要删除供应商「{provider}」的所有配置吗？此操作不可撤销。"),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dlg(dlg)),
                ft.TextButton("删除", on_click=on_confirm,
                              style=ft.ButtonStyle(color=ft.Colors.RED)),
            ],
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    # ── 模型 chips 切换 ──

    def _refresh_model_chips(self, provider):
        self._model_chips.controls.clear()
        if not provider:
            self._model_chips.visible = False
            return
        entries = [e for e in self.config.llm_list if e.get("provider") == provider and e.get("model")]
        if not entries:
            self._model_chips.visible = False
            return
        self._model_chips.visible = True
        current_model = self._s_custom_model.value.strip()
        for entry in entries:
            mn = entry["model"]
            is_current = mn == current_model
            self._model_chips.controls.append(ft.Chip(
                label=ft.Text(mn, size=12),
                selected=is_current,
                on_click=lambda e, ent=entry: self._switch_model(provider, ent),
            ))

    def _switch_model(self, provider, entry):
        self._provider_keys[self._provider_val] = self._s_apikey.value
        self._s_custom_model.value = entry.get("model", "")
        self._s_base_url.value = entry.get("base_url", "")
        self._s_apikey.value = entry.get("api_key", "")
        self._s_temp.value = str(entry.get("temperature", 0.7))
        self._s_max_tok.value = str(entry.get("max_tokens", 10240))
        self._s_mem_size.value = str(entry.get("context_window", 80))
        self._s_vision.value = bool(entry.get("supports_vision", False))
        self._model_val = entry.get("model", "")
        self._refresh_model_chips(provider)
        prov_keys = {e["provider"]: e.get("api_key", "") for e in self.config.llm_list if e.get("api_key")}
        if provider in prov_keys:
            self._provider_keys[provider] = prov_keys[provider]
        self._mark_dirty()
        self.page.update()
