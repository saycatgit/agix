"""验证 CupertinoDatePicker.value 是否在用户滚动时正确更新"""
import flet as ft
from datetime import datetime

def main(page: ft.Page):
    page.title = "CupertinoDatePicker Value 测试"
    page.window.width = 400
    page.window.height = 500

    picker_ref = ft.Ref[ft.CupertinoDatePicker]()
    output = ft.Text("尚未选择", size=14)

    def show_picker(_):
        dlg = ft.AlertDialog(
            title=ft.Text("选择时间"),
            content=ft.Container(
                content=ft.CupertinoDatePicker(
                    ref=picker_ref,
                    value=datetime.now(),
                    date_order=ft.DatePickerDateOrder.YEAR_MONTH_DAY,
                    minute_interval=1,
                    mode=ft.CupertinoDatePickerMode.DATE_AND_TIME,
                ),
                width=300, height=250,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: page.close(dlg)),
                ft.TextButton("确定", on_click=lambda e: confirm(e, dlg)),
            ],
        )
        page.open(dlg)

    def confirm(_, dlg):
        p = picker_ref.current
        if p:
            initial = datetime.now()
            picker_val = p.value
            output.value = (
                f"初始值(datetime.now()): {initial}\n"
                f"picker.value:          {picker_val}\n"
                f"strftime:              {picker_val.strftime('%Y-%m-%d %H:%M:%S') if picker_val else 'NONE'}\n"
                f"初始值>=picker值:       {initial >= picker_val if picker_val else 'N/A'}"
            )
            output.update()
        page.close(dlg)

    page.add(
        ft.ElevatedButton("打开选择器", on_click=show_picker),
        output,
    )

ft.app(target=main)
