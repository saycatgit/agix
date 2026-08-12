"""最小验证：Flet v0.85.3 Web 客户端是否支持运行时修改 TextField.suffix。

服务端：TextField(宽400) + Toggle 按钮。
点击 Toggle 在 suffix=None 与 suffix=IconButton 之间切换。
用 ASGI 方式导出，由 uvicorn 启动，避免自动打开浏览器。
"""
import flet as ft

_STATE = {"show_suffix": False}


def _build_suffix_btn():
    return ft.IconButton(icon=ft.Icons.ADD, icon_size=20, tooltip="suffix-probe")


def main(page: ft.Page):
    page.window.width = 800
    page.window.height = 500
    page.window.left = 0
    page.window.top = 0
    page.padding = 10

    field = ft.TextField(width=400, hint_text="input")

    def toggle(e):
        _STATE["show_suffix"] = not _STATE["show_suffix"]
        field.suffix = _build_suffix_btn() if _STATE["show_suffix"] else None
        btn.text = "ON" if _STATE["show_suffix"] else "OFF"
        btn.update()
        field.update()
        page.update()

    btn = ft.ElevatedButton("OFF", on_click=toggle)
    page.add(field, btn)


if __name__ == "__main__":
    import uvicorn
    from flet import app as flet_app

    app = flet_app(main, export_asgi_app=True, view=ft.AppView.WEB_BROWSER,
                   host="127.0.0.1", port=8599, no_cdn=True)
    uvicorn.run(app, host="127.0.0.1", port=8599, log_level="warning")
