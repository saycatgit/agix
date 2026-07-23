#!/usr/bin/env python3
"""
打印 Flet 中所有图标的名称和代码。
用法: python3 test/test_flet_icons.py [--all]
  不带参数: 仅打印基础图标（2231个）
  --all   : 打印全部（含 OUTLINED/ROUNDED/SHARP 变体，共8825个）
"""
import sys
import flet as ft


def main():
    show_all = "--all" in sys.argv
    icons = ft.icons.Icons
    all_attrs = sorted(a for a in dir(icons) if not a.startswith("_"))

    if not show_all:
        all_attrs = [a for a in all_attrs if not a.endswith(("_OUTLINED", "_ROUNDED", "_SHARP"))]

    print(f"共 {len(all_attrs)} 个图标：\n")
    print(f"{'序号':>5}  {'名称':<40}  {'代码'}")
    print("-" * 80)

    for i, attr in enumerate(all_attrs, 1):
        icon = getattr(icons, attr)
        print(f"{i:>5}  {icon.name:<40}  ft.icons.Icons.{icon.name}")

    print("\n" + "=" * 80)
    print(f"基础图标: 2231  完整(含变体): 8825")
    print(f'代码中使用: ft.icons.Icons.ICON_NAME  例如 ft.icons.Icons.ACCESSIBILITY')


if __name__ == "__main__":
    main()
