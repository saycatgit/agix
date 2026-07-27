"""任务面板 UI 组件 —— 可拖拽、半透明悬浮任务监控面板"""

import asyncio
import flet as ft


def task_msg(text: str, style: str, style_visuals: dict, default_style: str) -> ft.Container:
    """构建单条任务消息气泡"""
    v = style_visuals.get(style, style_visuals.get(default_style, {}))
    return ft.Container(
        content=ft.Text(text, size=12, selectable=True),
        bgcolor=v.get("bg", ft.Colors.GREY_50),
        border_radius=6,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        padding=ft.Padding(left=8, right=8, top=4, bottom=4),
    )


class TaskPanel:
    """任务面板 —— 悬浮拖拽窗口，展示任务进度/步骤/思考"""

    # ── 可覆盖的默认样式 ──
    PANEL_WIDTH: int = 800
    PANEL_HEIGHT: int = 500
    PANEL_BGCOLOR = ft.Colors.WHITE
    TITLE_BGCOLOR = ft.Colors.GREY_100
    STATUS_BGCOLOR = ft.Colors.BLUE_50
    DIVIDER_COLOR = ft.Colors.GREY_300
    THINK_DIVIDER_COLOR = ft.Colors.ORANGE_200
    BORDER_RADIUS: int = 10
    SHADOW = ft.BoxShadow(spread_radius=1, blur_radius=12, color=ft.Colors.BLACK26)

    TASK_LABEL: str = "📋 任务"
    STATUS_LABEL: str = "进度"
    ACTION_LABEL: str = "步骤"
    THINK_LABEL: str = "思考"
    ASK_HINT: str = "回答 Agent..."
    CLOSE_TOOLTIP: str = "关闭任务面板"

    LABEL_SIZE: int = 10
    STOP_TOOLTIP: str = "停止任务"
    END_TOOLTIP: str = "结束执行"
    SEND_TOOLTIP: str = "发送"
    LABEL_COLOR = ft.Colors.GREY_500
    TITLE_SIZE: int = 13
    TITLE_WEIGHT = ft.FontWeight.W_600
    MSG_TEXT_SIZE: int = 12
    ASK_TEXT_SIZE: int = 12

    INITIAL_LEFT: int = 420
    INITIAL_TOP: int = 60
    HOVER_OPACITY: float = 0.3
    FULL_OPACITY: float = 1.0

    STATUS_PANEL_WIDTH: int = 200

    def __init__(
        self,
        page: ft.Page,
        eqm,
        style_visuals: dict,
        msg_style,
        on_close=None,
        thinking_enabled: bool = True,
    ):
        self.page = page
        self.eqm = eqm
        self._style_visuals = style_visuals
        self._M = msg_style  # MsgStyle 命名空间
        self._thinking_enabled = thinking_enabled
        self._on_close = on_close

        self._panel_pos = [self.INITIAL_LEFT, self.INITIAL_TOP]
        self._drag_start = [self.INITIAL_LEFT, self.INITIAL_TOP]
        self._hover_cnt = 0

        self._input_focused = False
        self._paused = False

        # 暴露给外部轮询的控件
        self.status_text: ft.Text = None
        self.action_list: ft.ListView = None
        self.think_list: ft.ListView = None
        self.ask_container: ft.Container = None
        self.ask_input: ft.TextField = None
        self._panel: ft.Container = None
        self._wrapper: ft.GestureDetector = None
        self._name_ref: ft.Ref[ft.Text] = ft.Ref[ft.Text]()

        self._build()


    # ── 公共属性 ──

    @property
    def wrapper(self) -> ft.GestureDetector:
        return self._wrapper

    @property
    def visible(self) -> bool:
        return self._wrapper.visible if self._wrapper else False

    @visible.setter
    def visible(self, val: bool):
        if self._wrapper:
            self._wrapper.visible = val

    @property
    def name_ref(self):
        return self._name_ref

    # ── 公共方法 ──

    def on_switch_change(self, e):
        """task_switch.on_change 回调"""
        self.visible = e.control.value
        if e.control.value:
            self._panel.opacity = self.HOVER_OPACITY
            self.page.update()

    def add_message(self, text: str, style: str):
        """根据 style 路由到步骤列表或思考列表"""
        w = task_msg(text, style, self._style_visuals, self._M.ASSISTANT)
        if style == self._M.THINKING:
            self.think_list.controls.append(w)
        else:
            self.action_list.controls.append(w)

    def set_status(self, text: str):
        self.body_status_text.value = text
        self.body_status_text.update()

    def set_task_name(self, name: str):
        truncated = name[:50] + "..." if len(name) > 50 else name
        if self._name_ref.current:
            self._name_ref.current.value = truncated

    def set_ask_visible(self, visible: bool):
        self.ask_container.visible = visible

    # ── 内部构建 ──

    def _build(self):
        self._build_widgets()
        self._build_panel()
        self._build_wrapper()

    def _build_widgets(self):
        self.status_text = ft.Text("", size=self.MSG_TEXT_SIZE, selectable=True)
        self.body_status_text = ft.Text("", size=self.MSG_TEXT_SIZE, selectable=True)
        self.action_list = ft.ListView(expand=True, spacing=4, padding=0, auto_scroll=True)
        self.think_list = ft.ListView(expand=True, spacing=4, padding=0, auto_scroll=True)

        self.ask_input = ft.TextField(
            hint_text=self.ASK_HINT,
            border=ft.InputBorder.OUTLINE,
            border_color=ft.Colors.GREY_300,
            border_radius=6,
            multiline=True,
            min_lines=2,
            max_lines=3,
            expand=True,
            text_size=self.ASK_TEXT_SIZE,
            dense=True,
            on_focus=lambda e: setattr(self, '_input_focused', True),
            on_blur=lambda e: setattr(self, '_input_focused', False),
        )
        self.ask_input.on_change = lambda e: self._toggle_ask_action_btn()
        self._ask_action_btn = ft.IconButton(
            icon=ft.Icons.STOP, icon_size=22,
            tooltip=self.STOP_TOOLTIP, on_click=lambda e: self._stop(),
        )
        self.ask_container = ft.Container(
            content=ft.Row([self.ask_input, self._ask_action_btn], spacing=4),
            padding=ft.Padding(0, 4, 0, 0),
            visible=True,
        )

    def _build_panel(self):
        self._panel = ft.Container(
            opacity=self.FULL_OPACITY,
            width=self.PANEL_WIDTH,
            height=self.PANEL_HEIGHT,
            border_radius=ft.BorderRadius(
                self.BORDER_RADIUS, self.BORDER_RADIUS,
                self.BORDER_RADIUS, self.BORDER_RADIUS,
            ),
            bgcolor=self.PANEL_BGCOLOR,
            shadow=self.SHADOW,
            content=ft.Column([
                self._build_title_bar(),
                self._build_body(),
            ], spacing=0, expand=True),
        )

    def _build_title_bar(self):
        return ft.GestureDetector(
            content=ft.Container(
                content=ft.Row([
                    ft.Text(
                        self.TASK_LABEL, width=60,
                        weight=self.TITLE_WEIGHT, size=self.TITLE_SIZE,
                    ),
                    ft.Text(
                        "", size=self.LABEL_SIZE + 2,
                        weight=self.TITLE_WEIGHT,
                        ref=self._name_ref,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE, icon_size=16,
                        tooltip=self.CLOSE_TOOLTIP,
                        on_click=lambda e: self._close(),
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                bgcolor=self.TITLE_BGCOLOR,
                border_radius=ft.BorderRadius(
                    self.BORDER_RADIUS, self.BORDER_RADIUS, 0, 0,
                ),
                padding=ft.Padding(12, 8, 8, 8),
            ),
            on_pan_start=self._on_drag_start,
            on_pan_update=self._on_drag_task_panel,
            on_enter=self._panel_enter,
            on_exit=self._panel_exit,
        )

    def _build_body(self):
        return ft.Container(
            content=ft.Row([
                # 左侧：进度面板
                ft.Container(
                    content=ft.Column([
                        ft.Text(
                            self.STATUS_LABEL, size=self.LABEL_SIZE,
                            color=self.LABEL_COLOR, weight=self.TITLE_WEIGHT,
                        ),
                        ft.Container(content=self.body_status_text, expand=True),
                    ], spacing=2, expand=True),
                    width=self.STATUS_PANEL_WIDTH,
                    padding=ft.Padding(8, 6, 8, 6),
                    bgcolor=self.STATUS_BGCOLOR,
                ),
                ft.VerticalDivider(width=1, color=self.DIVIDER_COLOR),
                # 右侧：步骤 + 思考（thinking 关闭时思考区隐藏）
                ft.Container(
                    content=ft.Column([
                        ft.Column([
                            ft.Text(
                                self.ACTION_LABEL, size=self.LABEL_SIZE,
                                color=self.LABEL_COLOR, weight=self.TITLE_WEIGHT,
                            ),
                            ft.Container(content=self.action_list, expand=True),
                        ], spacing=2, expand=2),
                        ft.Divider(height=1, color=self.DIVIDER_COLOR,
                                   visible=self._thinking_enabled),
                        self._build_think_section(),
                        ft.Divider(height=1, color=self.THINK_DIVIDER_COLOR,
                                   visible=self._thinking_enabled),
                        self.ask_container,
                    ], spacing=0),
                    expand=True,
                    padding=ft.Padding(6, 0, 6, 0),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
            ], spacing=0),
            expand=True,
            padding=ft.Padding(6, 4, 6, 6),
        )


    def _build_think_section(self) -> ft.Column:
        """构建思考区域，visible 受 thinking_enabled 控制"""
        self._think_section = ft.Column([
            ft.Text(
                self.THINK_LABEL, size=self.LABEL_SIZE,
                color=self.LABEL_COLOR, weight=self.TITLE_WEIGHT,
            ),
            ft.Container(content=self.think_list, expand=True),
        ], spacing=2, expand=3, visible=self._thinking_enabled)
        return self._think_section

    def _build_wrapper(self):
        self._wrapper = ft.GestureDetector(
            content=self._panel,
            on_enter=self._panel_enter,
            on_exit=self._panel_exit,
        )
        self._wrapper.left = self._panel_pos[0]
        self._wrapper.top = self._panel_pos[1]
        self._wrapper.visible = False

    # ── 拖拽 & 悬停 ──

    def _on_drag_start(self, e):
        self._drag_start[0] = self._panel_pos[0]
        self._drag_start[1] = self._panel_pos[1]

    def _on_drag_task_panel(self, e: ft.DragUpdateEvent):
        self._panel_pos[0] = self._drag_start[0] + e.global_delta.x
        self._panel_pos[1] = self._drag_start[1] + e.global_delta.y
        self._panel_pos[0] = max(0, min(self._panel_pos[0], self.page.window.width - 640))
        self._panel_pos[1] = max(0, min(self._panel_pos[1], self.page.window.height - 400))
        self._wrapper.left = self._panel_pos[0]
        self._wrapper.top = self._panel_pos[1]

    def _stop(self):
        if not self._paused:
            self.eqm.send_control("stop", mode="task")
            self._paused = True
            self.eqm.send_display("正在暂停...", mode="task")
            self._toggle_ask_action_btn()
        else:
            self.eqm.send_control("end", mode="task")
            self._paused = False
            self._toggle_ask_action_btn()

    def _panel_enter(self, e):
        self._hover_cnt += 1
        self._panel.opacity = self.FULL_OPACITY
        self.page.update()

    def _panel_exit(self, e):
        self._hover_cnt = max(0, self._hover_cnt - 1)
        if self._hover_cnt == 0:
            self._panel.opacity = self.HOVER_OPACITY
            self.page.update()

    # ── 关闭 & 发送 ──

    def _close(self):
        if self._on_close:
            self._on_close()
        self.visible = False
        self._hover_cnt = 0
        self._panel.opacity = self.HOVER_OPACITY
        self.page.update()

    def _toggle_ask_action_btn(self):
        """按钮三态：暂停中→结束, 有内容→发送, 无内容→停止"""
        if self._paused:
            self._ask_action_btn.icon = ft.Icons.CANCEL
            self._ask_action_btn.tooltip = self.END_TOOLTIP
            self._ask_action_btn.on_click = lambda e: self._stop()
            self._ask_action_btn.update()
            return
        if self.ask_input.value.strip():
            self._ask_action_btn.icon = ft.Icons.SEND
            self._ask_action_btn.tooltip = self.SEND_TOOLTIP
            self._ask_action_btn.on_click = lambda e: self._send()
        else:
            self._ask_action_btn.icon = ft.Icons.STOP
            self._ask_action_btn.tooltip = self.STOP_TOOLTIP
            self._ask_action_btn.on_click = lambda e: self._stop()
        self._ask_action_btn.update()

    def _on_page_keyboard(self, e: ft.KeyboardEvent):
        # print(f"[DEBUG] _on_page_keyboard: key={e.key!r}, ctrl={e.ctrl}, shift={e.shift}, focused={self._input_focused}")
        if not self._input_focused:
            return
        if e.key == "Enter" and not e.ctrl and not e.shift:
            # print("[DEBUG] Enter → calling _send()")
            self._send()
        elif e.key == "Enter" and e.ctrl:
            # print("[DEBUG] Ctrl+Enter → inserting newline")
            self.ask_input.value += "\n"
            self.ask_input.update()

    def _send(self):
        t = self.ask_input.value.strip()
        # print(f"[DEBUG] _send: value={self.ask_input.value!r}, stripped={t!r}")
        if not t:
            return
        self._paused = False
        self.action_list.controls.append(
            task_msg(t, self._M.USER, self._style_visuals, self._M.ASSISTANT)
        )
        self.eqm.respond_to_ask(
            t, msg_id=self.eqm.get_pending_ask_id("task"), mode="task"
        )
        self.ask_input.value = ""
        self.page.update()
        self._toggle_ask_action_btn()

        async def _refocus():
            await asyncio.sleep(0.1)
            await self.ask_input.focus()
            self.ask_input.value = ""
            self.page.update()
            self._toggle_ask_action_btn()
        self.page.run_task(_refocus)
