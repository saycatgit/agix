"""Flet UI —— 双标签 (Chat / Task) 界面, 通过 EventQueueManager 与工作线程通信"""

import asyncio
import flet as ft
from event_queue_manager import EventQueueManager
import os
import uuid
import webbrowser


def build_ui(page: ft.Page, eqm: EventQueueManager, agent):
    """构建并挂载 Flet 界面"""

    # 窗口默认隐藏，安心设置无边框属性
    page.window.title_bar_hidden = True
    page.window.frameless = True

    page.title = "Agix"
    page.window.width = 900
    page.window.height = 600
    page.padding = 0

    # ── 自定义标题栏 ──
    def _minimize(e):
        page.window.minimized = True

    def _close_window(e):
        async def _do_close():
            try:
                await page.window.close()
            except Exception:
                pass
        page.run_task(_do_close)

    title_bar = ft.Container(
        content=ft.Row([
            ft.WindowDragArea(
                content=ft.Row([
                    ft.Text("🤖", size=18),
                    ft.Text("Agix AI Assistant", size=14),
                ]),
                expand=True,
            ),
            ft.IconButton(
                icon=ft.Icons.SETTINGS,
                icon_size=18,
                tooltip="设置",
                on_click=lambda e: _open_settings(page),
            ),
            ft.IconButton(
                icon=ft.Icons.MINIMIZE,
                icon_size=18,
                tooltip="最小化",
                on_click=_minimize,
            ),
            ft.IconButton(
                icon=ft.Icons.CLOSE,
                icon_size=18,
                tooltip="关闭",
                on_click=_close_window,
            ),
        ], spacing=0),
        bgcolor=ft.Colors.SURFACE,
        padding=ft.Padding(left=12, right=4, top=4, bottom=4),
        height=40,
    )

    # ── 消息渲染辅助 ──

    def _msg_container(text: str, is_user: bool = False, is_ask: bool = False,
                       style: str = ""):
        if is_user:
            bg = ft.Colors.GREEN_50
            label = "👤 你"
        elif is_ask:
            bg = ft.Colors.ORANGE_50
            label = "❓ Agix 提问"
        elif style == "error":
            bg = ft.Colors.RED_50
            label = "❌ 错误"
        elif style == "warn":
            bg = ft.Colors.AMBER_50
            label = "⚠️ 警告"
        else:
            bg = ft.Colors.GREY_50
            label = "🤖 Agix"
        return ft.Container(
            content=ft.Column([
                ft.Text(label, size=11, color=ft.Colors.GREY_600, weight=ft.FontWeight.BOLD),
                ft.Text(text, size=14, selectable=True),
            ], spacing=2),
            bgcolor=bg,
            border_radius=10,
            padding=ft.Padding(left=14, right=14, top=10, bottom=10),
        )

    def _right_align(widget):
        return ft.Row([widget], alignment=ft.MainAxisAlignment.END)

    # ── Chat 面板 ──
    chat_list = ft.ListView(expand=True, spacing=8, padding=15, auto_scroll=True)
    chat_ask_badge = ft.Text("", size=12, color=ft.Colors.ORANGE, visible=False)

    chat_input = ft.TextField(
        hint_text="输入消息...",
        border_radius=10,
        min_lines=1,
        max_lines=5,
        expand=True,
        text_size=14,
    )

    def send_chat(e=None):
        text = chat_input.value.strip()
        if not text:
            return
        if eqm.is_asking("chat"):
            msg_id = eqm.get_pending_ask_id("chat")
            chat_list.controls.append(_right_align(_msg_container(text, is_user=True)))
            eqm.respond_to_ask(text, msg_id=msg_id, mode="chat")
        else:
            chat_list.controls.append(_right_align(_msg_container(text, is_user=True)))
            eqm.send_user_input(text, mode="chat")
        chat_input.value = ""
        page.update()
        page.run_task(chat_input.focus)

    chat_input.on_submit = lambda e: send_chat()

    chat_panel = ft.Column([
        ft.Container(content=chat_list, expand=True),
        ft.Divider(height=1),
        ft.Row([chat_ask_badge], alignment=ft.MainAxisAlignment.START),
        ft.Container(
            content=ft.Row([
                chat_input,
                ft.IconButton(
                    icon=ft.Icons.SEND,
                    on_click=lambda e: send_chat(),
                    icon_size=20,
                ),
            ]),
            padding=ft.Padding(left=10, right=10, top=6, bottom=10),
        ),
    ], expand=True, spacing=0, visible=True)

    # ── Task 面板 ──
    task_list = ft.ListView(expand=True, spacing=8, padding=15, auto_scroll=True)
    task_ask_badge = ft.Text("", size=12, color=ft.Colors.ORANGE, visible=False)

    task_input = ft.TextField(
        hint_text="输入消息...",
        border_radius=10,
        min_lines=1,
        max_lines=5,
        expand=True,
        text_size=14,
    )

    def send_task(e=None):
        text = task_input.value.strip()
        if not text:
            return
        if eqm.is_asking("task"):
            msg_id = eqm.get_pending_ask_id("task")
            task_list.controls.append(_right_align(_msg_container(text, is_user=True)))
            eqm.respond_to_ask(text, msg_id=msg_id, mode="task")
        else:
            task_list.controls.append(_right_align(_msg_container(text, is_user=True)))
            eqm.send_user_input(text, mode="task")
        task_input.value = ""
        page.update()
        page.run_task(task_input.focus)

    task_input.on_submit = lambda e: send_task()

    task_panel = ft.Column([
        ft.Container(content=task_list, expand=True),
        ft.Divider(height=1),
        ft.Row([task_ask_badge], alignment=ft.MainAxisAlignment.START),
        ft.Container(
            content=ft.Row([
                task_input,
                ft.IconButton(
                    icon=ft.Icons.SEND,
                    on_click=lambda e: send_task(),
                    icon_size=20,
                ),
            ]),
            padding=ft.Padding(left=10, right=10, top=6, bottom=10),
        ),
    ], expand=True, spacing=0, visible=False)

    # ── Tab 切换栏 (用按钮代替 Tabs, 兼容 Flet 0.85) ──
    selected_tab = 0

    def switch_tab(idx):
        nonlocal selected_tab
        selected_tab = idx
        chat_panel.visible = (idx == 0)
        task_panel.visible = (idx == 1)
        chat_btn.bgcolor = ft.Colors.PRIMARY_CONTAINER if idx == 0 else ft.Colors.TRANSPARENT
        task_btn.bgcolor = ft.Colors.PRIMARY_CONTAINER if idx == 1 else ft.Colors.TRANSPARENT
        page.update()

    chat_btn = ft.ElevatedButton(
        content=ft.Text("💬 Chat"),
        on_click=lambda e: switch_tab(0),
        bgcolor=ft.Colors.PRIMARY_CONTAINER,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=0)),
    )
    task_btn = ft.ElevatedButton(
        content=ft.Text("📋 Tasks"),
        on_click=lambda e: switch_tab(1),
        bgcolor=ft.Colors.TRANSPARENT,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=0)),
    )

    tab_bar = ft.Row(
        [chat_btn, task_btn],
        alignment=ft.MainAxisAlignment.START,
        spacing=0,
    )

    # ── 页面布局 ──
    page.add(
        title_bar,
        ft.Column([
            tab_bar,
            ft.Divider(height=1),
            chat_panel,
            task_panel,
        ], expand=True, spacing=0)
    )

    # ── 消息添加函数 ──
    def _add_to_list(lst, msg, is_user=False):
        is_ask = msg.get("message_type") == "ask"
        style = msg.get("style", "")
        lst.controls.append(_msg_container(
            msg.get("content", ""), is_user=is_user, is_ask=is_ask,
            style=style,
        ))

    # ── 异步轮询器 ──
    async def poll_queues():
        while True:
            for msg in eqm.drain_display("chat"):
                _add_to_list(chat_list, msg)
            for msg in eqm.drain_display("task"):
                _add_to_list(task_list, msg)

            # 更新 ask 徽章
            if eqm.is_asking("chat"):
                chat_ask_badge.value = "⏳ 等待你的回答..."
                chat_ask_badge.visible = True
            else:
                chat_ask_badge.visible = False

            if eqm.is_asking("task"):
                task_ask_badge.value = "⏳ 等待你的回答..."
                task_ask_badge.visible = True
            else:
                task_ask_badge.visible = False

            page.update()
            await asyncio.sleep(0.3)

    page.run_task(poll_queues)

    # 界面就绪，显示窗口
    page.window.visible = True
    page.update()

    # ── 初始欢迎（窗口显示后再添加）──
    chat_list.controls.append(_msg_container(
        "你好！我是 Agix，你的 AI 开发助手。\n"
        "我可以帮你写代码、管理任务、回答问题。\n"
        "• Chat 标签页: 直接对话\n"
        "• Tasks 标签页: 查看定时任务输出"
    ))
    task_list.controls.append(_msg_container("任务输出将显示在这里。"))

    page.window.icon = "/home/agent_native/logo.ico"
    page.update()





def _open_settings(page: ft.Page):
    """打开设置对话框"""
    dlg = ft.AlertDialog(
        title=ft.Text("设置"),
        content=ft.Text("设置面板（待实现）"),
    )
    page.show_dialog(dlg)


# ── 登录界面 ──

def build_login_view(page: ft.Page, on_login_success, server_url: str = "http://127.0.0.1:5000"):
    """构建 RFC 8252 登录界面 —— 点击按钮 → 打开浏览器 → 轮询 token → 回调 on_login_success(token)"""

    page.window.title_bar_hidden = True
    page.window.frameless = True
    page.title = "Agix"
    page.window.width = 720
    page.window.height = 620
    page.padding = 0

    # ── 标题栏 ──
    def _close_window(e):
        async def _do_close():
            try:
                await page.window.close()
            except Exception:
                pass
        page.run_task(_do_close)

    title_bar = ft.Container(
        content=ft.Row([
            ft.WindowDragArea(
                content=ft.Row([
                    ft.Text("🤖", size=18),
                    ft.Text("Agix", size=14),
                ]),
                expand=True,
            ),
            ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="关闭", on_click=_close_window),
        ], spacing=0),
        bgcolor=ft.Colors.SURFACE,
        padding=ft.Padding(left=12, right=4, top=4, bottom=4),
        height=40,
    )

    # ── 登录区域 ──
    status_text = ft.Text("", size=13, color=ft.Colors.GREY_600)

    def on_login_click(e):
        try:
            login_btn.disabled = True
            login_btn.text = "等待浏览器登录..."
            status_text.value = "正在打开登录页..."
            page.update()

            # 生成唯一 session_id，关联浏览器和桌面端
            session_id = uuid.uuid4().hex[:12]
            login_url = f"{server_url}/login?session_id={session_id}"
            webbrowser.open(login_url)
            status_text.value = "已打开浏览器，请在浏览器中完成登录"
            page.update()

            # 轮询服务端取 token
            import urllib.request as _ur
            async def poll_token():
                import json as _json
                poll_url = f"{server_url}/api/poll_login?session_id={session_id}"
                while True:
                    await asyncio.sleep(0.5)
                    try:
                        resp = _ur.urlopen(poll_url, timeout=3)
                        data = _json.loads(resp.read())
                        token = data.get("token")
                        if token:
                            expires_at = data.get("expires_at", 0)
                            on_login_success(token, expires_at)
                            return
                    except Exception:
                        pass  # 服务器暂时不可达，继续轮询

            page.run_task(poll_token)
        except Exception as ex:
            login_btn.disabled = False
            login_btn.text = "手机登录"
            status_text.value = f"错误: {ex}"
            page.update()

    login_btn = ft.ElevatedButton(
        content=ft.Text("手机登录", size=15),
        on_click=on_login_click,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=6),
            padding=ft.Padding(20, 12, 20, 12),
        ),
    )

    content = ft.Column([
        ft.Container(height=40),
        ft.Text("🤖", size=48),
        ft.Text("Agix", size=24, weight=ft.FontWeight.W_600),
        ft.Text("AI 开发助手", size=14, color=ft.Colors.GREY_600),
        ft.Container(height=24),
        login_btn,
        ft.Container(height=8),
        status_text,
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    page.add(title_bar, content)
    page.window.visible = True
    page.update()

