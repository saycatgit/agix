#!/usr/bin/env python3
"""SSH管理脚本
用法:
  添加SSH: python3 ssh_manager.py add '<json_config>'
  删除SSH: python3 ssh_manager.py del <SSH名称>
  列出SSH: python3 ssh_manager.py list

JSON 配置字段: name(必填), host(必填), port(必填), username(必填),
              auth_type(必填, password/key), password(可选), key_path(可选), desc(必填)

示例:
  python3 ssh_manager.py add '{"name":"my-ecs","host":"1.2.3.4","port":22,"username":"root","auth_type":"key","key_path":"keys/my_key","desc":"阿里云ECS"}'
  python3 ssh_manager.py del my-ecs
"""

import json
import sys
import os


SSH_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(SSH_DIR, "ssh.json")
MD_PATH = os.path.join(SSH_DIR, "ssh.md")


def load_json_config():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_connections():
    """兼容 ssh.json 顶层为列表或 {"connections": [...]} 字典两种格式"""
    data = load_json_config()
    if isinstance(data, list):
        return data
    return data.get("connections", [])


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
    """找到「当前SSH」表格的起止行号（从 0 开始），没有则返回 None"""
    in_section = False
    table_start = None
    table_end = None
    for i, line in enumerate(lines):
        if line.strip() == "## 当前SSH":
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith("|") and "---" not in stripped.replace(" ", "").replace("-", "").replace("|", ""):
                if table_start is None:
                    table_start = i
                table_end = i
            elif table_start is not None and not stripped.startswith("|"):
                break
    if table_start is not None and table_end is not None:
        return table_start, table_end
    return None


def add_to_md(name, host, port, username, auth_type):
    lines = read_md_lines()
    table_range = find_table_range(lines)
    if table_range is None:
        print(f"错误: 在 {MD_PATH} 中未找到「当前SSH」表格")
        sys.exit(1)
    _, table_end = table_range
    new_line = f"| `{name}` | {host} | {port} | {username} | {auth_type} |\n"
    lines.insert(table_end + 1, new_line)
    save_md_lines(lines)
    print(f"[ssh.md] 已添加SSH: {name}")


def del_from_md(name):
    lines = read_md_lines()
    table_range = find_table_range(lines)
    if table_range is None:
        print(f"错误: 在 {MD_PATH} 中未找到「当前SSH」表格")
        sys.exit(1)
    table_start, table_end = table_range
    mark = f"| `{name}` |"
    removed = False
    new_lines = []
    for i, line in enumerate(lines):
        if table_start <= i <= table_end and mark in line:
            removed = True
            continue
        new_lines.append(line)
    if not removed:
        print(f"警告: 在「当前SSH」表格中未找到 {name}")
    else:
        save_md_lines(new_lines)
        print(f"[ssh.md] 已删除SSH: {name}")


def cmd_add(config_json):
    config = json.loads(config_json)
    required = ["name", "host", "port", "username", "auth_type", "desc"]
    for key in required:
        if key not in config:
            print(f"错误: 缺少必填字段 '{key}'")
            sys.exit(1)

    name = config["name"]
    auth_type = config["auth_type"]
    if auth_type not in ("password", "key"):
        print(f"错误: auth_type 必须为 password 或 key，当前值: {auth_type}")
        sys.exit(1)

    entry = {
        "name": name,
        "host": config["host"],
        "port": config["port"],
        "username": config["username"],
        "auth_type": auth_type,
    }
    if auth_type == "password":
        entry["password"] = config.get("password", "")
        entry["key_path"] = ""
    else:
        entry["key_path"] = config.get("key_path", "")
        entry["password"] = ""

    # 更新 ssh.json
    connections = load_connections()
    # 检查是否已存在同名SSH
    existing_idx = None
    for i, conn in enumerate(connections):
        if conn.get("name") == name:
            existing_idx = i
            break
    if existing_idx is not None:
        print(f"警告: SSH {name} 已存在，将覆盖配置")
        connections[existing_idx] = entry
    else:
        connections.append(entry)
    save_json_config(connections)
    print(f"[ssh.json] 已添加SSH: {name}")

    # 更新 ssh.md
    add_to_md(name, config["host"], str(config["port"]), config["username"], auth_type)

    print(f"完成: SSH {name} 已添加")


def cmd_del(name):
    # 更新 ssh.json
    connections = load_connections()
    new_connections = [c for c in connections if c.get("name") != name]
    if len(new_connections) == len(connections):
        print(f"警告: SSH {name} 在 ssh.json 中不存在")
    else:
        save_json_config(new_connections)
        print(f"[ssh.json] 已删除SSH: {name}")

    # 更新 ssh.md
    del_from_md(name)

    print(f"完成: SSH {name} 已删除")


def cmd_list():
    connections = load_connections()
    if not connections:
        print("(无SSH)")
        return
    for conn in connections:
        auth_info = f"key={conn.get('key_path', '')}" if conn.get("auth_type") == "key" else "password"
        print(f"  {conn['name']}: {conn['username']}@{conn['host']}:{conn['port']} ({auth_info})")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    if action == "add":
        if len(sys.argv) < 3:
            print("用法: python3 ssh_manager.py add '<json_config>'")
            sys.exit(1)
        cmd_add(sys.argv[2])
    elif action == "del":
        if len(sys.argv) < 3:
            print("用法: python3 ssh_manager.py del <SSH名称>")
            sys.exit(1)
        cmd_del(sys.argv[2])
    elif action == "list":
        cmd_list()
    else:
        print(f"未知操作: {action}，支持 add/del/list")
        sys.exit(1)


if __name__ == "__main__":
    main()
