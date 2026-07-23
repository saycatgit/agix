#!/usr/bin/env python3
"""
三步修改 status_sidebar.py：
1. 添加 TaskAttributeManager/TaskManager 导入
2. 在 _show_task_menu 中添加"添加子任务"菜单项
3. 在 _confirm_delete_task 前插入 _add_subtask 方法（使用 TaskAttributeManager + TaskManager）
"""
import sys, re

filepath = "/home/agent_native/src/flet_ui/status_sidebar.py"

with open(filepath, "r") as f:
    lines = f.readlines()

# ═══ 步骤 1: 添加 import ═══
if not any("TaskAttributeManager" in l for l in lines):
    # 找到 "import flet as ft" 行，在其后插入
    for i, l in enumerate(lines):
        if l.strip() == "import flet as ft":
            lines.insert(i + 1, "from task_attribute_manager import TaskAttributeManager\n")
            lines.insert(i + 2, "from task_manager import TaskManager\n")
            print(f"Step 1: imports inserted after line {i+1}")
            break

# ═══ 步骤 2: 添加"添加子任务"菜单项 ═══
# 找到 _show_task_menu 中的 "删除任务" 行，在其前插入菜单项
for i, l in enumerate(lines):
    if 'ft.TextButton("删除任务", on_click=lambda e: self._confirm_delete_and_close(task, dlg)),' in l:
        indent = " " * 16  # 匹配该行缩进
        lines.insert(i, f'{indent}ft.TextButton("添加子任务", on_click=lambda e: self._add_subtask(task)),\n')
        print(f"Step 2: menu item inserted at line {i+1}")
        break

# ═══ 步骤 3: 插入 _add_subtask 方法 =══
# 找到 "    def _confirm_delete_task(self, task: dict):" 在前插入
insert_idx = None
for i, l in enumerate(lines):
    if l == "    def _confirm_delete_task(self, task: dict):\n":
        insert_idx = i
        break

if insert_idx is None:
    print("ERROR: _confirm_delete_task not found!")
    sys.exit(1)

new_method = '''
    def _add_subtask(self, task: dict):
        """添加子任务到当前任务"""
        state_file = task.get("state_file", "")
        if not state_file or not os.path.exists(state_file):
            return

        # 使用 TaskAttributeManager 加载类型/子类型配置
        task_config_path = os.path.join(self.task_dir, "task_config.json")
        attr_mgr = TaskAttributeManager(task_config_path)
        cat_names = attr_mgr.get_category_names()

        cat_options = [ft.dropdown.Option(c) for c in cat_names]

        name_field = ft.TextField(label="子任务名称", dense=True, height=40, text_size=13,
                                  content_padding=ft.Padding(12, 8, 12, 8))
        detail_field = ft.TextField(label="描述", dense=True, multiline=True, min_lines=2, max_lines=4,
                                    text_size=13, content_padding=ft.Padding(12, 8, 12, 8))
        path_field = ft.TextField(label="路径", dense=True, height=40, text_size=13, read_only=True,
                                  content_padding=ft.Padding(12, 8, 12, 8), expand=True)

        path_row = ft.Row([path_field,
                           ft.IconButton(icon=ft.Icons.FOLDER_OPEN, icon_size=18, tooltip="选择文件夹",
                                         on_click=lambda e: self._pick_folder(path_field))], spacing=4)

        cat_dd = ft.Dropdown(label="类型", dense=True, height=40, text_size=13,
                             options=cat_options)
        subtype_dd = ft.Dropdown(label="子类型", dense=True, height=40, text_size=13,
                                 options=[])

        def on_cat_change(e):
            subtypes = attr_mgr.get_subtypes_by_cat(cat_dd.value)
            subtype_dd.options = [ft.dropdown.Option(st[0]) for st in subtypes]
            subtype_dd.value = None
            self.page.update()

        cat_dd.on_change = on_cat_change

        content_col = ft.Column([
            name_field,
            detail_field,
            path_row,
            cat_dd,
            subtype_dd,
        ], spacing=10, width=440)

        def on_save(e):
            has_error = False
            for fld, msg in [(name_field, "请输入子任务名称"),
                              (detail_field, "请输入描述"),
                              (path_field, "请输入路径"),
                              (cat_dd, "请选择类型"),
                              (subtype_dd, "请选择子类型")]:
                if not fld.value:
                    fld.error = msg
                    has_error = True
                else:
                    fld.error = None
            self.page.update()
            if has_error:
                return

            try:
                task_mgr = TaskManager.load(state_file)
            except Exception:
                return
            item = {
                "sub_task_detail": detail_field.value,
                "sub_task_name": name_field.value,
                "task_type": cat_dd.value,
                "task_sub_type": f"{cat_dd.value}: {subtype_dd.value}",
                "dir_from": "temp",
            }
            index = len(task_mgr._subtasks)
            task_mgr.add_subtask(index, item)
            task_mgr.set_subtask_project(index, path_field.value)
            task_mgr.save()

            self._close_dialog(dlg)
            self.refresh()

        dlg = ft.AlertDialog(
            shape=ft.RoundedRectangleBorder(radius=3),
            title=ft.Text("添加子任务", size=16, weight=ft.FontWeight.BOLD),
            content=content_col,
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.FilledButton("保存", on_click=on_save),
            ],
        )
        self._open_dialog(dlg)

'''

lines.insert(insert_idx, new_method)
print(f"Step 3: _add_subtask inserted before line {insert_idx+1}")

# 写入
with open(filepath, "w") as f:
    f.writelines(lines)

print("Done. All 3 modifications applied.")
