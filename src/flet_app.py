"""Flet UI main module."""
import asyncio, uuid, webbrowser, flet as ft
from event_queue_manager import EventQueueManager, MsgType, MsgField, MsgStyle

_STYLE_VISUALS = {
    MsgStyle.USER:      {"bg": ft.Colors.GREEN_50,  "label": "你",         "label_size": 11, "italic": False, "text_size": 14, "label_color": ft.Colors.GREY_600, "label_weight": ft.FontWeight.BOLD},
    MsgStyle.ASSISTANT: {"bg": ft.Colors.GREY_50,   "label": "Agix",       "label_size": 11, "italic": False, "text_size": 14, "label_color": ft.Colors.GREY_600, "label_weight": ft.FontWeight.BOLD},
    MsgStyle.ASK:       {"bg": ft.Colors.ORANGE_50, "label": "Agix 提问",  "label_size": 11, "italic": True,  "text_size": 14, "label_color": ft.Colors.GREY_600, "label_weight": ft.FontWeight.BOLD},
    MsgStyle.ERROR:     {"bg": ft.Colors.RED_50,    "label": "错误",       "label_size": 11, "italic": False, "text_size": 14, "label_color": ft.Colors.GREY_600, "label_weight": ft.FontWeight.BOLD},
    MsgStyle.WARN:      {"bg": ft.Colors.AMBER_50,  "label": "警告",       "label_size": 11, "italic": False, "text_size": 14, "label_color": ft.Colors.GREY_600, "label_weight": ft.FontWeight.BOLD},
}

def build_ui(page: ft.Page, eqm: EventQueueManager, agent):
    page.window.title_bar_hidden = True
    page.window.frameless = True
    page.title = "Agix"
    page.window.width = 900
    page.window.height = 600
    page.padding = 0

    def _minimize(e):
        page.window.minimized = True
    def _close(e):
        async def _do(): await page.window.close()
        page.run_task(_do)

    tb = ft.Container(content=ft.Row([
        ft.WindowDragArea(content=ft.Row([ft.Text("🤖", size=18), ft.Text("Agix AI Assistant", size=14)]), expand=True),
        ft.IconButton(icon=ft.Icons.SETTINGS, icon_size=18, tooltip="设置", on_click=lambda e: _open_settings(page)),
        ft.IconButton(icon=ft.Icons.MINIMIZE, icon_size=18, tooltip="最小化", on_click=_minimize),
        ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="关闭", on_click=_close),
    ], spacing=0), bgcolor=ft.Colors.SURFACE, padding=ft.Padding(left=12,right=4,top=4,bottom=4), height=40)

    def _msg(text, is_user=False, is_ask=False, style=""):
        if is_user: v = _STYLE_VISUALS[MsgStyle.USER]
        elif is_ask: v = _STYLE_VISUALS[MsgStyle.ASK]
        elif style in _STYLE_VISUALS: v = _STYLE_VISUALS[style]
        else: v = _STYLE_VISUALS[MsgStyle.ASSISTANT]
        return ft.Container(content=ft.Column([
            ft.Text(v["label"], size=v.get("label_size",11), color=v.get("label_color",ft.Colors.GREY_600),
                weight=v.get("label_weight",ft.FontWeight.BOLD), italic=v.get("italic",False)),
            ft.Text(text, size=v.get("text_size",14), selectable=True),
        ], spacing=2), bgcolor=v["bg"], border_radius=10, padding=ft.Padding(left=14,right=14,top=10,bottom=10))

    def _r(w): return ft.Row([w], alignment=ft.MainAxisAlignment.END)

    # Chat
    cl = ft.ListView(expand=True, spacing=8, padding=15, auto_scroll=True)
    ca = ft.Text("", size=12, color=ft.Colors.ORANGE, visible=False)
    ci = ft.TextField(hint_text="输入消息...", border=ft.InputBorder.OUTLINE, border_color=ft.Colors.GREY_300,
        focused_border_color=ft.Colors.GREY_400, border_radius=10, min_lines=1, max_lines=5, expand=True, text_size=14)
    def _send(e=None):
        t = ci.value.strip()
        if not t: return
        if eqm.is_asking("chat"):
            cl.controls.append(_r(_msg(t, is_user=True)))
            eqm.respond_to_ask(t, msg_id=eqm.get_pending_ask_id("chat"), mode="chat")
        else:
            cl.controls.append(_r(_msg(t, is_user=True)))
            eqm.send_user_input(t, mode="chat")
        ci.value = ""; page.update()
    ci.on_submit = lambda e: _send()
    cp = ft.Column([ft.Container(content=cl, expand=True), ft.Divider(height=1),
        ft.Row([ca], alignment=ft.MainAxisAlignment.START),
        ft.Container(content=ft.Row([ci, ft.IconButton(icon=ft.Icons.SEND, on_click=lambda e: _send(), icon_size=20),
            ft.IconButton(icon=ft.Icons.STOP, on_click=lambda e: eqm.request_cancel("chat"), icon_size=20, tooltip="停止执行")]),
            padding=ft.Padding(left=10,right=10,top=6,bottom=10))], expand=True)

    page.add(tb, cp)

    def _al(lst, msg, is_user=False):
        is_ask = msg.get(MsgField.TYPE) == MsgType.ASK
        lst.controls.append(_msg(msg.get(MsgField.CONTENT,""), is_user=is_user, is_ask=is_ask,
            style=msg.get(MsgField.STYLE,"")))

    async def _poll():
        while True:
            for m in eqm.drain_display("chat"): _al(cl, m)
            for m in eqm.drain_display("task"):
                td = ft.AlertDialog(title=ft.Text("📋 Task"), content=ft.Text(m.get(MsgField.CONTENT,""), size=13, selectable=True))
                td.actions = [ft.TextButton("Close", on_click=lambda e: (setattr(td,'open',False), page.update()))]
                page.show_dialog(td)
            ca.visible = eqm.is_asking("chat")
            try: page.update()
            except RuntimeError: return
            await asyncio.sleep(0.3)
    page.run_task(_poll)

    page.window.visible = True
    page.update()
    cl.controls.append(_msg("你好！我是 Agix，你的 AI 开发助手。\n我可以帮你写代码、管理任务、回答问题。"))
    page.window.icon = "/home/agent_native/logo.ico"
    page.update()

def _open_settings(page: ft.Page):
    page.show_dialog(ft.AlertDialog(title=ft.Text("设置"), content=ft.Text("设置面板（待实现）")))

def build_login_view(page: ft.Page, on_login_success, server_url="http://127.0.0.1:5000"):
    page.window.title_bar_hidden = True; page.window.frameless = True
    page.title = "Agix"; page.window.width = 720; page.window.height = 620; page.padding = 0
    def _close(e):
        async def _do(): await page.window.close()
        page.run_task(_do)
    tb = ft.Container(content=ft.Row([
        ft.WindowDragArea(content=ft.Row([ft.Text("🤖",size=18), ft.Text("Agix",size=14)]), expand=True),
        ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="关闭", on_click=_close)], spacing=0),
        bgcolor=ft.Colors.SURFACE, padding=ft.Padding(left=12,right=4,top=4,bottom=4), height=40)
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
                        if d.get("token"): on_login_success(d["token"], d.get("expires_at",0)); return
                    except Exception: pass
            page.run_task(_p)
        except Exception as ex:
            login_btn.disabled = False; login_btn.text = "手机登录"; st.value = f"错误: {ex}"; page.update()
    login_btn = ft.ElevatedButton(content=ft.Text("手机登录", size=15), on_click=_login,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6), padding=ft.Padding(20,12,20,12)))
    page.add(tb, ft.Column([ft.Container(height=40), ft.Text("🤖",size=48), ft.Text("Agix",size=24,weight=ft.FontWeight.W_600),
        ft.Text("AI 开发助手",size=14,color=ft.Colors.GREY_600), ft.Container(height=24), login_btn, ft.Container(height=8), st],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER))
    page.window.visible = True; page.update()
