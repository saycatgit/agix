"""聊天面板 UI 组件"""

import os, re, subprocess, asyncio
import flet as ft


def _clean_url(url: str) -> str:
    """清理 URL 尾部标点符号（半角/全角），返回干净的 URL。"""
    trailing = '.,;:!?)]}"\'' + '\u3002\uff0c\uff1b\uff1a\uff01\uff1f\u3001\uff09\u3015\u3017\u300d\u300f'
    while url and url[-1] in trailing:
        url = url[:-1]
    return url


# URL 正则：匹配裸 https?:// 开头的 URL
# - (?<![<(]) 防止匹配 markdown 链接语法 [text](url) 和已被包裹的 <url>
# - 排除空白、CJK 字符、全角标点、尖括号、方括号等，确保 CJK 文本中 URL 正确截断
_URL_PATTERN = re.compile(
    r'(?<![<(])https?://[^\s\u2E80-\u9FFF\uff00-\uffef\u3000-\u303f<>\[\]{}|]+'
)

class ChatPanel:
    """聊天面板 —— 消息列表、输入框、内联对话框、模型切换"""

    # ── 颜色/尺寸默认值 ──
    INPUT_BORDER_COLOR = ft.Colors.GREY_300
    INPUT_FOCUSED_BORDER_COLOR = ft.Colors.GREY_400
    INPUT_BORDER_RADIUS: int = 16
    INPUT_HINT: str = "输入消息..."

    ASK_COLOR = ft.Colors.ORANGE
    STATUS_BAR_BGCOLOR = ft.Colors.WHITE
    STATUS_BAR_HEIGHT: int = 32
    MODEL_LABEL_COLOR = ft.Colors.GREY_500
    WORK_DIR_COLOR = ft.Colors.GREY_500
    NO_MODEL_TEXT: str = "未配置"
    NO_KEY_SUFFIX: str = " (未配置)"
    WORK_DIR_PREFIX: str = "当前工作目录："

    INLINE_DIALOG_BGCOLOR = ft.Colors.ORANGE_50

    GREETING_TEXT: str = "你好！我是 Agix，你的 AI 开发助手。\n我可以帮你写代码、管理任务、回答问题。"
    STOPPING_TEXT: str = "正在停止..."

    SWITCH_TOOLTIP: str = "切换模型"
    WORK_DIR_TOOLTIP: str = "打开工作目录"
    SEND_TOOLTIP: str = "发送"
    STOP_TOOLTIP: str = "停止执行"
    END_TOOLTIP: str = "结束执行"
    CANCEL_LABEL: str = "取消"
    CONFIRM_LABEL: str = "确认"

    def __init__(
        self,
        page: ft.Page,
        eqm,
        agent,
        style_visuals: dict,
        avatar_data: dict,
        msg_style,
        msg_type,
        providers: dict,
    ):
        self.page = page
        self.eqm = eqm
        self.agent = agent
        self._style_visuals = style_visuals
        self._avatar_data = avatar_data
        self._MsgStyle = msg_style
        self._MsgType = msg_type
        self._providers = providers
        self._build()

        self._current_work_dir = self.agent.config.execution.work_dir
        self._input_focused = False
        self._paused = False

    async def _launch_url(self, url: str):
        await self.page.launch_url(url)

    # ── 对外接口 ──

    @property
    def container(self) -> ft.Column:
        return self._cp

    def add_message(self, msg_dict: dict):
        is_ask = msg_dict.get("message_type", "") == self._MsgType.ASK
        style = msg_dict.get("style", "")
        text = msg_dict.get("content", "")
        self._cl.controls.append(self._msg(text, is_user=False, is_ask=is_ask, style=style))
        while len(self._cl.controls) > 1000:
            self._cl.controls.pop(0)

    def set_asking(self, visible: bool):
        self._ca.visible = visible

    def show_password_dialog(self, question: str, msg_id: str, mode: str):
        pwd_field = ft.TextField(
            password=True, can_reveal_password=True,
            border=ft.InputBorder.OUTLINE, border_radius=6,
            autofocus=True, expand=True, text_size=14,
        )

        def _submit(e):
            self.eqm.respond_to_ask(pwd_field.value or "", msg_id=msg_id, mode=mode)
            self._inline_dialog.visible = False
            self.page.update()

        def _cancel(e):
            self.eqm.respond_to_ask("", msg_id=msg_id, mode=mode)
            self._inline_dialog.visible = False
            self.page.update()

        pwd_field.on_submit = _submit
        self._inline_dialog.content = ft.Row([
            ft.Text(question + "：", size=14),
            pwd_field,
            ft.TextButton(self.CANCEL_LABEL, on_click=_cancel),
            ft.ElevatedButton(self.CONFIRM_LABEL, on_click=_submit),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self._inline_dialog.visible = True
        self.page.update()

    def show_confirm_dialog(self, question: str, msg_id: str, mode: str):
        def _yes(e):
            self.eqm.respond_to_ask("是", msg_id=msg_id, mode=mode)
            self._inline_dialog.visible = False
            self.page.update()

        def _no(e):
            self.eqm.respond_to_ask("否", msg_id=msg_id, mode=mode)
            self._inline_dialog.visible = False
            self.page.update()

        self._inline_dialog.content = ft.Row([
            ft.Text(question, size=14),
            ft.TextButton("是", on_click=_yes),
            ft.TextButton("否", on_click=_no),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self._inline_dialog.visible = True
        self.page.update()

    def add_greeting(self):
        self._cl.controls.append(self._msg(self.GREETING_TEXT))

    # ── 构建 ──

    def _build(self):
        self._cl = ft.ListView(expand=True, spacing=8, padding=15, auto_scroll=True)
        self._ca = ft.Text("", size=12, color=self.ASK_COLOR, visible=False)
        self._mic_btn = ft.IconButton(icon=ft.Icons.MIC, icon_size=28, tooltip="语音输入", on_click=lambda e: self._voice_input())
        self._ci = ft.TextField(
            hint_text=self.INPUT_HINT, border=ft.InputBorder.OUTLINE,
            border_color=self.INPUT_BORDER_COLOR,
            focused_border_color=self.INPUT_FOCUSED_BORDER_COLOR,
            border_radius=self.INPUT_BORDER_RADIUS,
            suffix_icon=self._mic_btn,
            multiline=True,
            min_lines=2,  expand=True, text_size=14,
            on_focus=lambda e: (setattr(self, '_input_focused', True), self._toggle_action_btn()),
            on_blur=lambda e: (setattr(self, '_input_focused', False), self._toggle_action_btn()),
            on_change=lambda e: self._toggle_action_btn(),
        )
        self._ci.on_submit = lambda e: self._send()


        self._model_label = ft.Text(self._get_active_label(), size=13, color=self.MODEL_LABEL_COLOR)
        self._work_dir_text = ft.Text(
            self.WORK_DIR_PREFIX + self.agent.config.execution.work_dir,
            size=13, color=self.WORK_DIR_COLOR, overflow=ft.TextOverflow.ELLIPSIS,
        )

        sb_ctrl = ft.Container(content=ft.Row([
            ft.Row([
                self._work_dir_text,
                ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, icon_size=14,
                    tooltip=self.WORK_DIR_TOOLTIP, on_click=self._open_work_dir),
            ], spacing=4),
            ft.Row([
                self._model_label,
                ft.PopupMenuButton(
                    icon=ft.Icons.SWAP_HORIZ, icon_size=14,
                    tooltip=self.SWITCH_TOOLTIP,
                    items=[
                        ft.PopupMenuItem(
                            content=(e.get("label") or f"{e.get('provider','')}/{e.get('model','')}")
                                + (self.NO_KEY_SUFFIX if not e.get("api_key") else ""),
                            on_click=lambda e, i=idx: self._switch_to_model(i),
                            disabled=not e.get("api_key"),
                        )
                        for idx, e in enumerate(self.agent.config.llm_list)
                    ],
                ),
            ], spacing=4),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=self.STATUS_BAR_BGCOLOR, height=self.STATUS_BAR_HEIGHT,
            padding=ft.Padding(left=8, right=8, top=4, bottom=4),
        )

        self._inline_dialog = ft.Container(
            visible=False,
            bgcolor=self.INLINE_DIALOG_BGCOLOR,
            padding=ft.padding.Padding(12, 10, 12, 10),
        )

        self._action_btn = ft.IconButton(icon=ft.Icons.STOP, on_click=lambda e: self._stop(), icon_size=24, tooltip=self.STOP_TOOLTIP)

        self._cp = ft.Column([
            ft.Container(content=self._cl, expand=True),
            # ft.Divider(height=1),
            self._inline_dialog,
            ft.Row([self._ca], alignment=ft.MainAxisAlignment.START),
            ft.Container(content=ft.Row([
                self._ci,
                self._action_btn,
            ]), padding=ft.Padding(left=10, right=10, top=6, bottom=4)),
            sb_ctrl,
        ], expand=True)

    def _toggle_action_btn(self):
        """按钮三态：暂停中→结束, 有内容→发送, 无内容→停止"""
        if self._paused:
            self._action_btn.icon = ft.Icons.CANCEL
            self._action_btn.tooltip = self.END_TOOLTIP
            self._action_btn.on_click = lambda e: self._stop()
            self._ci.suffix_icon = None
            self._action_btn.update()
            self._ci.update()
            return
        if self._ci.value.strip():
            self._action_btn.icon = ft.Icons.SEND
            self._action_btn.tooltip = self.SEND_TOOLTIP
            self._action_btn.on_click = lambda e: self._send()
            self._ci.suffix_icon = None
        else:
            self._action_btn.icon = ft.Icons.STOP
            self._action_btn.tooltip = self.STOP_TOOLTIP
            self._action_btn.on_click = lambda e: self._stop()
            if self._input_focused:
                self._ci.suffix_icon = self._mic_btn
            else:
                self._ci.suffix_icon = None
        self._action_btn.update()
        self._ci.update()

    # ── 发送 / 停止 ──

    def _send(self):
        t = self._ci.value.strip()
        if not t:
            return
        self._paused = False
        if self.eqm.is_asking("chat"):
            self._cl.controls.append(self._r(self._msg(t, is_user=True)))
            self.eqm.respond_to_ask(t, msg_id=self.eqm.get_pending_ask_id("chat"), mode="chat")
        else:
            self._cl.controls.append(self._r(self._msg(t, is_user=True)))
            self.eqm.send_user_input(t, mode="chat")
        self._ci.value = ""
        self._ci.update()
        self._toggle_action_btn()

        async def _refocus():
            await asyncio.sleep(0.1)
            await self._ci.focus()
            self._ci.value = ""
            self._ci.update()
            self._toggle_action_btn()
        self.page.run_task(_refocus)

    def _on_page_keyboard(self, e: ft.KeyboardEvent):
        if not self._input_focused:
            return
        if e.key == "Enter" and not e.ctrl and not e.shift:
            # Enter → 发送消息
            self._send()
        elif e.key == "Enter" and e.ctrl:
            # Ctrl+Enter → 插入换行
            self._ci.value += "\n"
            self._ci.update()


    def _stop(self):
        if not self._paused:
            self.eqm.send_control("stop", mode="chat")
            self._paused = True
            self._toggle_action_btn()
        else:
            self.eqm.send_control("end", mode="chat")
            self._paused = False
            self._toggle_action_btn()

    def _voice_input(self):
        snack = ft.SnackBar(ft.Text("语音输入功能开发中..."), open=True)
        self.page.overlay.append(snack)
        self.page.update()

    # ── 模型切换 ──

    def _get_active_label(self) -> str:
        for e in self.agent.config.llm_list:
            if e.get("active") and e.get("api_key"):
                return e.get("label") or f"{e.get('provider','')}/{e.get('model','')}"
        return self.NO_MODEL_TEXT

    def _switch_to_model(self, idx: int):
        self.agent.config.switch_llm(idx)
        self.agent.config.save()
        self.agent.chat_llm.model = self.agent.config.llm.model
        self.agent.chat_llm.api_key = self.agent.config.llm.api_key
        self._model_label.value = self._get_active_label()
        self.page.update()

    # ── 工作目录 ──

    def update_work_dir(self, path: str = ""):
        """更新显示的工作目录"""
        if not path:
            path = self.agent.config.execution.work_dir
        self._current_work_dir = path
        self._work_dir_text.value = self.WORK_DIR_PREFIX + path
        self._work_dir_text.update()

    def _open_work_dir(self, e):
        wd = self._current_work_dir
        if self.agent.config.system == "windows":
            os.startfile(wd)
        else:
            subprocess.Popen(["xdg-open", wd])

    # ── 消息渲染辅助 ──

    def _r(self, w):
        return ft.Row([w], alignment=ft.MainAxisAlignment.END)

    def _avatar(self, style_type: str) -> ft.Container:
        char, color = self._avatar_data.get(style_type, ("?", ft.Colors.GREY))
        text_color = ft.Colors.GREEN if color is None else ft.Colors.WHITE
        return ft.Container(
            content=ft.Text(char, size=18, color=text_color, text_align=ft.TextAlign.CENTER),
            width=32, height=32, border_radius=16, bgcolor=color,
        )

    def _msg(self, text, is_user=False, is_ask=False, style=""):
        MsgStyle = self._MsgStyle
        style_type = MsgStyle.ASSISTANT
        if is_user:
            style_type = MsgStyle.USER
        elif is_ask:
            style_type = MsgStyle.ASK
        elif style in self._style_visuals:
            style_type = style
        v = self._style_visuals[style_type]
        avatar = self._avatar(style_type)
        italic = v.get("italic", False)
        # CJK 相邻 URL 修复：用尖括号包裹裸 URL，确保 GITHUB_WEB autolink 可识别
        text = _URL_PATTERN.sub(lambda m: f'<{_clean_url(m.group(0))}>', text)
        md_text = f"*{text}*" if italic else text
        bubble = ft.Container(
            content=ft.Markdown(
                md_text,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                auto_follow_links=True,
                on_tap_link=lambda e: self.page.run_task(self._launch_url, e.data),
                selectable=True,
            ),
            bgcolor=v["bg"], border_radius=10,
            padding=ft.Padding(left=14, right=14, top=10, bottom=10),
        )
        if is_user:
            return ft.Row([
                ft.Column([bubble], expand=True, horizontal_alignment=ft.CrossAxisAlignment.END),
                avatar,
            ], spacing=8, expand=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        return ft.Row([
            avatar,
            ft.Column([bubble], expand=True, horizontal_alignment=ft.CrossAxisAlignment.START),
        ], spacing=8, expand=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)
