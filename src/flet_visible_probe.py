"""最小验证10：Row 内联布局下 IconButton.visible 双向切换（最终候选方案）。

布局：state_text + Row([TextField(固定宽400), image_btn, action_btn]) + TOGGLE(独立行)。
点击 TOGGLE 切换 image_btn.visible（服务端 state 驱动，验证按钮固定不漂移）。
判定：image_btn 区 A→B、B→C 均 > 阈值 且 A→C ≤ 阈值 → Row 布局 visible 双向支持。
"""
import flet as ft

_STATE = {"show": True}


def main(page: ft.Page):
    page.window.width = 800
    page.window.height = 500
    page.window.left = 0
    page.window.top = 0
    page.padding = 10

    image_btn = ft.IconButton(ft.Icons.ADD, icon_size=24)
    tf = ft.TextField(width=400, height=56)
    action_btn = ft.ElevatedButton("SEND")
    row = ft.Row([tf, image_btn, action_btn])
    state_text = ft.Text("ON")

    def toggle(e):
        _STATE["show"] = not _STATE["show"]
        image_btn.visible = _STATE["show"]
        state_text.value = "ON" if _STATE["show"] else "OFF"
        page.update()

    btn = ft.ElevatedButton("TOGGLE", on_click=toggle)
    page.add(ft.Row([state_text]), row, btn)


if __name__ == "__main__":
    import uvicorn
    from flet import app as flet_app

    app = flet_app(main, export_asgi_app=True, view=ft.AppView.WEB_BROWSER,
                   host="127.0.0.1", port=8599, no_cdn=True)
    uvicorn.run(app, host="127.0.0.1", port=8599, log_level="warning")
