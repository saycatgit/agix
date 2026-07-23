"""Flet 图标浏览器 — 可视化浏览所有 Material Icons"""
import flet as ft


def main(page: ft.Page):
    page.title = "Flet Icons 浏览器"
    page.window.width = 1100
    page.window.height = 800
    page.theme_mode = ft.ThemeMode.LIGHT

    icons_proxy = ft.icons.Icons
    # 仅基础图标，排除变体
    all_icons = sorted(
        a for a in dir(icons_proxy)
        if not a.startswith("_") and not a.endswith(("_OUTLINED", "_ROUNDED", "_SHARP"))
    )

    PAGE_SIZE = 80
    current_page = 0
    total_pages = (len(all_icons) + PAGE_SIZE - 1) // PAGE_SIZE

    def get_page_icons():
        start = current_page * PAGE_SIZE
        end = start + PAGE_SIZE
        return all_icons[start:end]

    # --- UI 组件 ---
    search_field = ft.TextField(
        hint_text="搜索图标名称...",
        prefix_icon=ft.icons.Icons.SEARCH,
        dense=True,
        expand=True,
    )

    page_label = ft.Text(f"共 {len(all_icons)} 个图标", size=13)

    icon_grid = ft.GridView(
        expand=True,
        runs_count=6,
        child_aspect_ratio=1.3,
        spacing=6,
        run_spacing=6,
    )

    status_bar = ft.Text(size=11, color=ft.Colors.GREY_500)

    def copy_icon(e, icon_name):
        page.set_clipboard(f"ft.icons.Icons.{icon_name}")
        status_bar.value = f"已复制: ft.icons.Icons.{icon_name}"
        status_bar.update()

    def render_icons(icon_names):
        icon_grid.controls.clear()
        for name in icon_names:
            icon = getattr(icons_proxy, name)
            icon_grid.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(icon, size=28, color=ft.Colors.BLUE_GREY_700),
                            ft.Text(
                                name,
                                size=9,
                                text_align=ft.TextAlign.CENTER,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                    ),
                    on_click=lambda e, n=name: copy_icon(e, n),
                    padding=ft.Padding(4, 6, 4, 6),
                    border_radius=4,
                    ink=True,
                    tooltip=f"ft.icons.Icons.{name}",
                )
            )
        icon_grid.update()

    def update_pagination():
        page_label.value = (
            f"共 {len(all_icons)} 个图标  第 {current_page + 1}/{total_pages} 页"
        )
        page_label.update()

    def go_page(delta):
        nonlocal current_page
        new_page = current_page + delta
        if 0 <= new_page < total_pages:
            current_page = new_page
            render_icons(get_page_icons())
            update_pagination()

    def on_search(e):
        nonlocal current_page
        query = search_field.value.strip().upper()
        if not query:
            current_page = 0
            render_icons(get_page_icons())
            update_pagination()
            return

        filtered = [n for n in all_icons if query in n]
        current_page = 0
        page_label.value = f"搜索 '{search_field.value}': {len(filtered)} 个结果"
        page_label.update()
        icon_grid.controls.clear()
        for name in filtered[:200]:  # 限制显示数量
            icon = getattr(icons_proxy, name)
            icon_grid.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(icon, size=28, color=ft.Colors.BLUE_GREY_700),
                            ft.Text(
                                name, size=9, text_align=ft.TextAlign.CENTER,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                    ),
                    on_click=lambda e, n=name: copy_icon(e, n),
                    padding=ft.Padding(4, 6, 4, 6),
                    border_radius=4,
                    ink=True,
                    tooltip=f"ft.icons.Icons.{name}",
                )
            )
        icon_grid.update()

    # 防抖搜索
    search_field.on_change = on_search

    # --- 布局 ---
    page.add(
        ft.Row(
            [
                ft.Text("🎨 Flet Icons 浏览器", size=18, weight=ft.FontWeight.BOLD),
                page_label,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        ft.Row(
            [
                search_field,
                ft.IconButton(
                    ft.icons.Icons.CHEVRON_LEFT,
                    on_click=lambda e: go_page(-1),
                    tooltip="上一页",
                ),
                ft.IconButton(
                    ft.icons.Icons.CHEVRON_RIGHT,
                    on_click=lambda e: go_page(1),
                    tooltip="下一页",
                ),
            ]
        ),
        icon_grid,
        status_bar,
    )

    # 初始渲染
    render_icons(get_page_icons())
    update_pagination()


if __name__ == "__main__":
    ft.app(target=main)
