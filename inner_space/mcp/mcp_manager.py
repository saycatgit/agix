#!/usr/bin/env python3
"""MCP 服务器管理脚本
用法:
  添加服务器: python3 mcp_manager.py add '<json_config>'
  删除服务器: python3 mcp_manager.py del <server_name>

JSON 配置字段: name(必填), command(必填), args(数组,可选), env(对象,可选), cwd(路径,可选), desc(说明,必填)

示例:
  python3 mcp_manager.py add '{"name":"amap","command":"node","args":["/path/to/index.js"],"env":{"KEY":"val"},"desc":"高德地图服务"}'
  python3 mcp_manager.py del amap
"""

import json
import sys
import os


MCP_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(MCP_DIR, "mcp.json")
MD_PATH = os.path.join(MCP_DIR, "mcp.md")


def load_json_config():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_config(config):
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_md_lines():
    with open(MD_PATH, "r", encoding="utf-8") as f:
        return f.readlines()


def save_md_lines(lines):
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


def find_table_range(lines):
    """找到「可用服务器」表格的起止行号（从 1 开始），没有则返回 None"""
    in_table_section = False
    table_start = None
    table_end = None
    for i, line in enumerate(lines):
        if line.strip() == "## 可用服务器":
            in_table_section = True
            continue
        if in_table_section:
            stripped = line.strip()
            if stripped.startswith("|") and "---" not in stripped.replace(" ", "").replace("-", "").replace("|", ""):
                if table_start is None:
                    table_start = i  # 表头行
                table_end = i  # 持续更新为最后一行数据行
            elif table_start is not None and not stripped.startswith("|"):
                break  # 表格结束
    if table_start is not None and table_end is not None:
        return table_start, table_end
    return None


def add_to_md(server_name, desc):
    lines = read_md_lines()
    table_range = find_table_range(lines)
    if table_range is None:
        print(f"错误: 在 {MD_PATH} 中未找到「可用服务器」表格")
        sys.exit(1)
    _, table_end = table_range
    new_line = f"| `{server_name}` | {desc} |\n"
    lines.insert(table_end + 1, new_line)
    save_md_lines(lines)
    print(f"[mcp.md] 已添加服务器: {server_name}")


def del_from_md(server_name):
    lines = read_md_lines()
    table_range = find_table_range(lines)
    if table_range is None:
        print(f"错误: 在 {MD_PATH} 中未找到「可用服务器」表格")
        sys.exit(1)
    table_start, table_end = table_range
    mark = f"| `{server_name}` |"
    removed = False
    new_lines = []
    for i, line in enumerate(lines):
        if table_start <= i <= table_end and mark in line:
            removed = True
            continue
        new_lines.append(line)
    if not removed:
        print(f"警告: 在「可用服务器」表格中未找到 {server_name}")
    else:
        save_md_lines(new_lines)
        print(f"[mcp.md] 已删除服务器: {server_name}")


def cmd_add(config_json):
    config = json.loads(config_json)
    required = ["name", "command", "desc"]
    for key in required:
        if key not in config:
            print(f"错误: 缺少必填字段 '{key}'")
            sys.exit(1)

    name = config["name"]
    server_entry = {"command": config["command"]}
    if "args" in config:
        server_entry["args"] = config["args"]
    if "env" in config:
        server_entry["env"] = config["env"]
    if "cwd" in config:
        server_entry["cwd"] = config["cwd"]
    if "desc" in config:
        server_entry["desc"] = config["desc"]

    # 更新 mcp.json
    json_config = load_json_config()
    if "servers" not in json_config:
        json_config["servers"] = {}
    if name in json_config["servers"]:
        print(f"警告: 服务器 {name} 已存在，将覆盖配置")
    json_config["servers"][name] = server_entry
    save_json_config(json_config)
    print(f"[mcp.json] 已添加服务器: {name}")

    # 更新 mcp.md
    add_to_md(name, config["desc"])

    print(f"完成: 服务器 {name} 已添加")


def cmd_del(name):
    # 更新 mcp.json
    json_config = load_json_config()
    servers = json_config.get("servers", {})
    if name not in servers:
        print(f"警告: 服务器 {name} 在 mcp.json 中不存在")
    else:
        del servers[name]
        save_json_config(json_config)
        print(f"[mcp.json] 已删除服务器: {name}")

    # 更新 mcp.md
    del_from_md(name)

    print(f"完成: 服务器 {name} 已删除")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    if action == "add":
        if len(sys.argv) < 3:
            print("用法: python3 mcp_manager.py add '<json_config>'")
            sys.exit(1)
        cmd_add(sys.argv[2])
    elif action == "del":
        if len(sys.argv) < 3:
            print("用法: python3 mcp_manager.py del <server_name>")
            sys.exit(1)
        cmd_del(sys.argv[2])
    else:
        print(f"未知操作: {action}，支持 add/del")
        sys.exit(1)


if __name__ == "__main__":
    main()
