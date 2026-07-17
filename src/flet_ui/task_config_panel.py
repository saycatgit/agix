"""任务配置面板 UI 组件"""

import json
import flet as ft


class TaskConfigPanel:
    """任务配置面板 —— 管理 task_config.json（主任务/子任务/prompt/phases）"""

    PANEL_WIDTH: int = 920
    PANEL_HEIGHT: int = 560
    PANEL_BGCOLOR = ft.Colors.WHITE
    TITLE_BGCOLOR = ft.Colors.GREY_100
    SIDEBAR_BGCOLOR = ft.Colors.GREY_50
    DIVIDER_COLOR = ft.Colors.GREY_300
    BORDER_RADIUS: int = 10
    SHADOW = ft.BoxShadow(spread_radius=1, blur_radius=12, color=ft.Colors.BLACK26)

    LABEL_COLOR = ft.Colors.GREY_500
    TITLE_TEXT: str = "📋 任务配置"
    CAT_LABEL: str = "主任务类型"
    SUB_LABEL: str = "子任务"
    CONFIG_LABEL: str = "配置"
    PROMPT_LABEL: str = "Prompt"
    PHASES_LABEL: str = "Phases"
    SAVE_LABEL: str = "保存"
    SAVE_TOOLTIP: str = "保存到配置文件"
    CLOSE_TOOLTIP: str = "关闭"
    PLACEHOLDER_CAT: str = "主任务类型"
    PLACEHOLDER_SUB: str = "子任务类型"
    PLACEHOLDER_PROMPT: str = "填写子任务对应的系统提示词 prompt 行"
    PLACEHOLDER_PHASE: str = "填写子任务必须的阶段 phase 名称"
    COMMON_MARKER: str = "..."
    _UNSAVED: str = "● 未保存"

    TF_DEFAULTS: dict = {"dense": True, "text_size": 13}
    PROMPT_BORDER = ft.Colors.TEAL_200
    PHASE_BORDER: str = ft.Colors.PURPLE_200
    PHASE_MSG_BORDER: str = ft.Colors.PURPLE_100
    SUB_BORDER: str = ft.Colors.BLUE_200
    BTN_STYLE = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=4), padding=ft.Padding(6, 4, 6, 4))

    def __init__(self, page: ft.Page, config):
        self.page = page
        self.config = config
        self._file_path = config.paths.task_config_file_path
        self._data = self._load()
        self._cat_idx: int | None = None
        self._sub_idx: int | None = None
        self._dirty = False

        # 子控件引用
        self._cat_list = ft.ListView(spacing=2, expand=True)
        self._sub_list = ft.ListView(spacing=2, expand=True)
        self._prompt_list = ft.ListView(spacing=2, expand=True)
        self._phases_list = ft.ListView(spacing=2, expand=True)
        self._config_title = ft.Text("", size=13, weight=ft.FontWeight.W_600)
        self._unsaved_badge = ft.Text("", size=11, color=ft.Colors.ORANGE_600)

        self._build()

    # ── 数据 I/O ──

    def _load(self) -> dict:
        with open(self._file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_to_disk(self):
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        self._dirty = False
        self._unsaved_badge.value = ""
        self.page.update()

    def _mark_dirty(self):
        self._dirty = True
        self._unsaved_badge.value = self._UNSAVED
        self.page.update()

    @property
    def panel(self) -> ft.Container:
        return self._panel

    def open(self):
        self._panel.visible = True
        self.page.update()

    def close(self):
        self._panel.visible = False
        self.page.update()

    # ── 辅助 ──

    def _current_category(self) -> dict | None:
        cats = self._data.get("categories", [])
        if self._cat_idx is not None and 0 <= self._cat_idx < len(cats):
            return cats[self._cat_idx]
        return None

    def _current_subtype(self) -> dict | None:
        cat = self._current_category()
        if cat is None or self._sub_idx is None:
            return None
        subs = cat.get("subtypes", [])
        if 0 <= self._sub_idx < len(subs):
            return subs[self._sub_idx]
        return None

    def _find_config(self, cat: dict, sub_name: str | None) -> dict | None:
        """查找匹配的 subtask_config；sub_name=None 则返回通用配置"""
        configs = cat.get("subtask_config", [])
        if sub_name is None:
            for c in configs:
                if c.get("match_subtypes") == [self.COMMON_MARKER]:
                    return c
            return None
        for c in configs:
            if sub_name in c.get("match_subtypes", []):
                return c
        return None

    def _get_or_create_config(self, cat: dict, sub_name: str | None) -> dict:
        cfg = self._find_config(cat, sub_name)
        if cfg is not None:
            return cfg
        if "subtask_config" not in cat:
            cat["subtask_config"] = []
        new_cfg = {
            "match_subtypes": [sub_name] if sub_name else [self.COMMON_MARKER],
            "prompt": [],
            "phases": [],
        }
        cat["subtask_config"].append(new_cfg)
        self._mark_dirty()
        return new_cfg

    # ── 构建 ──

    def _build(self):
        tf = self.TF_DEFAULTS
        # 左栏 —— 主任务
        self._tf_cat = ft.TextField(hint_text=self.PLACEHOLDER_CAT, **tf,
            expand=True, border_color=ft.Colors.GREY_300)
        left = ft.Column([
            ft.Text(self.CAT_LABEL, size=12, color=self.LABEL_COLOR),
            self._cat_list,
            ft.Row([self._tf_cat,
                ft.IconButton(icon=ft.Icons.ADD, icon_size=18, tooltip="添加主任务",
                    on_click=lambda e: self._add_category())], spacing=4),
        ], expand=1, spacing=4)

        # 中栏 —— 子任务
        self._tf_sub = ft.TextField(hint_text=self.PLACEHOLDER_SUB, **tf,
            expand=True, border_color=self.SUB_BORDER)
        middle = ft.Column([
            ft.Text(self.SUB_LABEL, size=12, color=self.LABEL_COLOR),
            self._sub_list,
            ft.Row([self._tf_sub,
                ft.IconButton(icon=ft.Icons.ADD, icon_size=18, tooltip="添加子任务",
                    on_click=lambda e: self._add_subtype())], spacing=4),
        ], expand=1, spacing=4)

        # 右栏 —— 配置（prompt + phases）
        self._tf_prompt = ft.TextField(hint_text=self.PLACEHOLDER_PROMPT, **tf,
            expand=True, border_color=self.PROMPT_BORDER)
        self._tf_phase = ft.TextField(hint_text=self.PLACEHOLDER_PHASE, **tf,
            expand=True, border_color=self.PHASE_BORDER)
        right = ft.Column([
            ft.Row([self._config_title, self._unsaved_badge], spacing=8),
            ft.Divider(height=1, color=self.DIVIDER_COLOR),
            ft.Text(self.PROMPT_LABEL, size=12, color=self.LABEL_COLOR),
            ft.Column([
                self._prompt_list,
                ft.Row([self._tf_prompt,
                ft.IconButton(icon=ft.Icons.ADD, icon_size=18, tooltip="添加 prompt 行",
                    on_click=lambda e: self._add_prompt())], spacing=4),
            ], expand=1, spacing=4),
            ft.Divider(height=1, color=self.DIVIDER_COLOR),
            ft.Text(self.PHASES_LABEL, size=12, color=self.LABEL_COLOR),
            ft.Column([
                self._phases_list,
                ft.Row([self._tf_phase,
                ft.IconButton(icon=ft.Icons.ADD, icon_size=18, tooltip="添加 phase",
                    on_click=lambda e: self._add_phase())], spacing=4),
            ], expand=2, spacing=4),
            ft.Row([ft.ElevatedButton(self.SAVE_LABEL, on_click=lambda e: self._save_to_disk(),
                style=self.BTN_STYLE, tooltip=self.SAVE_TOOLTIP)],
                alignment=ft.MainAxisAlignment.END),
        ], expand=2, spacing=4)

        body = ft.Row([
            left, ft.VerticalDivider(width=1, color=self.DIVIDER_COLOR),
            middle, ft.VerticalDivider(width=1, color=self.DIVIDER_COLOR),
            right,
        ], expand=True, spacing=8)

        self._panel = ft.Container(
            opacity=1.0, width=self.PANEL_WIDTH, height=self.PANEL_HEIGHT,
            border_radius=ft.BorderRadius(self.BORDER_RADIUS, self.BORDER_RADIUS, self.BORDER_RADIUS, self.BORDER_RADIUS),
            bgcolor=self.PANEL_BGCOLOR, shadow=self.SHADOW, left=140, top=60, visible=False,
            content=ft.Column([
                ft.Container(content=ft.Row([
                    ft.Text(self.TITLE_TEXT, weight=ft.FontWeight.W_600, size=14, expand=True),
                    ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip=self.CLOSE_TOOLTIP,
                        on_click=lambda e: self.close()),
                ], spacing=6), bgcolor=self.TITLE_BGCOLOR, padding=ft.Padding(12, 8, 12, 8),
                    border_radius=ft.BorderRadius(self.BORDER_RADIUS, self.BORDER_RADIUS, 0, 0)),
                ft.Container(content=body, padding=ft.Padding(12, 8, 12, 8), expand=True),
            ], spacing=0, expand=True),
        )
        self._refresh_categories()


    # ── 左栏：主任务 CRUD ──

    def _refresh_categories(self):
        self._cat_list.controls.clear()
        cats = self._data.get("categories", [])
        for i, cat in enumerate(cats):
            idx = i
            name = cat.get("name", "")
            btn = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=14, tooltip="删除",
                on_click=lambda e, ii=idx: self._delete_category(ii))
            tile = ft.Container(
                content=ft.Row([ft.Text(name, size=13, expand=True), btn], spacing=2),
                padding=ft.Padding(6, 4, 6, 4), border_radius=4,
                bgcolor=self.SIDEBAR_BGCOLOR if idx == self._cat_idx else ft.Colors.TRANSPARENT,
                on_click=lambda e, ii=idx: self._select_category(ii),
                ink=True,
            )
            self._cat_list.controls.append(tile)
        self.page.update()

    def _select_category(self, idx: int):
        self._cat_idx = idx
        self._sub_idx = None
        self._refresh_categories()
        self._refresh_subtypes()
        self._refresh_config()

    def _add_category(self):
        name = (self._tf_cat.value or "").strip()
        if not name:
            return
        self._data.setdefault("categories", []).append({
            "name": name, "description": "", "subtypes": [], "subtask_config": [],
        })
        self._tf_cat.value = ""
        self._mark_dirty()
        self._refresh_categories()

    def _delete_category(self, idx: int):
        cats = self._data.get("categories", [])
        if 0 <= idx < len(cats):
            cats.pop(idx)
            if self._cat_idx == idx:
                self._cat_idx = None
                self._sub_idx = None
            elif self._cat_idx is not None and self._cat_idx > idx:
                self._cat_idx -= 1
            self._mark_dirty()
            self._refresh_categories()
            self._refresh_subtypes()
            self._refresh_config()

    # ── 中栏：子任务 CRUD ──

    def _refresh_subtypes(self):
        self._sub_list.controls.clear()
        cat = self._current_category()
        if cat is None:
            self.page.update()
            return
        subs = cat.get("subtypes", [])
        for i, sub in enumerate(subs):
            idx = i
            name = sub.get("name", "")
            btn = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=14, tooltip="删除子任务",
                on_click=lambda e, ii=idx: self._delete_subtype(ii))
            tile = ft.Container(
                content=ft.Row([ft.Text(name, size=13, expand=True), btn], spacing=2),
                padding=ft.Padding(6, 4, 6, 4), border_radius=4,
                bgcolor=ft.Colors.BLUE_50 if idx == self._sub_idx else ft.Colors.TRANSPARENT,
                on_click=lambda e, ii=idx: self._select_subtype(ii),
                ink=True,
            )
            self._sub_list.controls.append(tile)
        self.page.update()

    def _select_subtype(self, idx: int):
        self._sub_idx = idx
        self._refresh_subtypes()
        self._refresh_config()

    def _add_subtype(self):
        cat = self._current_category()
        if cat is None:
            return
        name = (self._tf_sub.value or "").strip()
        if not name:
            return
        cat.setdefault("subtypes", []).append({"name": name, "description": ""})
        self._tf_sub.value = ""
        self._mark_dirty()
        self._refresh_subtypes()

    def _delete_subtype(self, idx: int):
        cat = self._current_category()
        if cat is None:
            return
        subs = cat.get("subtypes", [])
        if 0 <= idx < len(subs):
            removed_name = subs[idx].get("name", "")
            subs.pop(idx)
            for cfg in cat.get("subtask_config", []):
                ms = cfg.get("match_subtypes", [])
                if removed_name in ms:
                    ms.remove(removed_name)
            if self._sub_idx == idx:
                self._sub_idx = None
            elif self._sub_idx is not None and self._sub_idx > idx:
                self._sub_idx -= 1
            self._mark_dirty()
            self._refresh_subtypes()
            self._refresh_config()

    # ── 右栏：Prompt / Phases ──

    def _active_config(self) -> dict | None:
        cat = self._current_category()
        if cat is None:
            return None
        if self._sub_idx is not None:
            sub = self._current_subtype()
            sub_name = sub["name"] if sub else None
        else:
            sub_name = None
        return self._get_or_create_config(cat, sub_name)

    def _refresh_config(self):
        self._prompt_list.controls.clear()
        self._phases_list.controls.clear()
        cfg = self._active_config()
        if cfg is None:
            self._config_title.value = self.CONFIG_LABEL
            self.page.update()
            return

        cat = self._current_category()
        sub = self._current_subtype()
        if sub:
            self._config_title.value = f"{self.CONFIG_LABEL} · {cat['name']} / {sub['name']}"
        else:
            self._config_title.value = f"{self.CONFIG_LABEL} · {cat['name']} / 通用"

        for i, line in enumerate(cfg.get("prompt", [])):
            idx = i
            tf = ft.TextField(value=line, **self.TF_DEFAULTS,
                expand=True, border_color=self.PROMPT_BORDER,
                on_change=lambda e, ii=idx: self._update_prompt(ii, e.control.value))
            btn = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=14, tooltip="删除",
                on_click=lambda e, ii=idx: self._delete_prompt(ii))
            self._prompt_list.controls.append(ft.Row([tf, btn], spacing=2))

        for i, ph in enumerate(cfg.get("phases", [])):
            p_idx = i
            # phase 名称行
            tf = ft.TextField(value=ph.get("name", ""), **self.TF_DEFAULTS,
                width=200, border_color=self.PHASE_BORDER,
                on_change=lambda e, pi=p_idx: self._update_phase(pi, e.control.value))
            del_btn = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=14, tooltip="删除 phase",
                on_click=lambda e, pi=p_idx: self._delete_phase(pi))
            msg_rows = []
            for j, msg in enumerate(ph.get("phase_msg", [])):
                m_idx = j
                mtf = ft.TextField(value=msg, **self.TF_DEFAULTS,
                    expand=True, border_color=self.PHASE_MSG_BORDER,
                    on_change=lambda e, pi=p_idx, mi=m_idx: self._update_phase_msg(pi, mi, e.control.value))
                mbtn = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=14, tooltip="删除 msg",
                    on_click=lambda e, pi=p_idx, mi=m_idx: self._delete_phase_msg(pi, mi))
                msg_rows.append(ft.Row([mtf, mbtn], spacing=2))
            # 添加 phase_msg 的行
            msg_tf = ft.TextField(hint_text="新增 msg", **self.TF_DEFAULTS,
                expand=True, border_color=self.PHASE_MSG_BORDER)
            add_msg_btn = ft.IconButton(icon=ft.Icons.ADD, icon_size=14, tooltip="添加 msg",
                on_click=lambda e, pi=p_idx, mtf_ref=msg_tf: self._add_phase_msg(pi, mtf_ref))
            msg_rows.append(ft.Row([msg_tf, add_msg_btn], spacing=2))
            # 组装 phase 卡片
            phase_block = ft.Column(
                [ft.Row([tf, del_btn], spacing=2)] + msg_rows,
                spacing=2,
            )
            self._phases_list.controls.append(ft.Container(
                content=phase_block, padding=ft.Padding(4, 4, 4, 4), border_radius=4,
                border=ft.Border(
                    top=ft.BorderSide(1, self.DIVIDER_COLOR),
                    bottom=ft.BorderSide(1, self.DIVIDER_COLOR),
                    left=ft.BorderSide(1, self.DIVIDER_COLOR),
                    right=ft.BorderSide(1, self.DIVIDER_COLOR),
                )))

        self.page.update()

    def _add_prompt(self):
        cfg = self._active_config()
        if cfg is None:
            return
        line = (self._tf_prompt.value or "").strip()
        if not line:
            return
        cfg.setdefault("prompt", []).append(line)
        self._tf_prompt.value = ""
        self._mark_dirty()
        self._refresh_config()

    def _delete_prompt(self, idx: int):
        cfg = self._active_config()
        if cfg is None:
            return
        prompts = cfg.get("prompt", [])
        if 0 <= idx < len(prompts):
            prompts.pop(idx)
            self._mark_dirty()
            self._refresh_config()

    def _update_prompt(self, idx: int, value: str):
        cfg = self._active_config()
        if cfg is None:
            return
        prompts = cfg.get("prompt", [])
        if 0 <= idx < len(prompts):
            prompts[idx] = value
            self._mark_dirty()

    def _add_phase(self):
        cfg = self._active_config()
        if cfg is None:
            return
        name = (self._tf_phase.value or "").strip()
        if not name:
            return
        cfg.setdefault("phases", []).append({"name": name, "phase_msg": []})
        self._tf_phase.value = ""
        self._mark_dirty()
        self._refresh_config()

    def _delete_phase(self, idx: int):
        cfg = self._active_config()
        if cfg is None:
            return
        phases = cfg.get("phases", [])
        if 0 <= idx < len(phases):
            phases.pop(idx)
            self._mark_dirty()
            self._refresh_config()

    def _update_phase(self, idx: int, value: str):
        cfg = self._active_config()
        if cfg is None:
            return
        phases = cfg.get("phases", [])
        if 0 <= idx < len(phases):
            phases[idx]["name"] = value
            self._mark_dirty()

    def _add_phase_msg(self, phase_idx: int, tf_ref):
        cfg = self._active_config()
        if cfg is None:
            return
        phases = cfg.get("phases", [])
        if not (0 <= phase_idx < len(phases)):
            return
        text = (tf_ref.value or "").strip()
        if not text:
            return
        phases[phase_idx].setdefault("phase_msg", []).append(text)
        tf_ref.value = ""
        self._mark_dirty()
        self._refresh_config()

    def _delete_phase_msg(self, phase_idx: int, msg_idx: int):
        cfg = self._active_config()
        if cfg is None:
            return
        phases = cfg.get("phases", [])
        if not (0 <= phase_idx < len(phases)):
            return
        msgs = phases[phase_idx].get("phase_msg", [])
        if 0 <= msg_idx < len(msgs):
            msgs.pop(msg_idx)
            self._mark_dirty()
            self._refresh_config()

    def _update_phase_msg(self, phase_idx: int, msg_idx: int, value: str):
        cfg = self._active_config()
        if cfg is None:
            return
        phases = cfg.get("phases", [])
        if not (0 <= phase_idx < len(phases)):
            return
        msgs = phases[phase_idx].get("phase_msg", [])
        if 0 <= msg_idx < len(msgs):
            msgs[msg_idx] = value
            self._mark_dirty()
