#!/usr/bin/env python3
"""skill-creator —— 创建新的 skill 目录结构，支持 CLI 和 MCP stdio 两种模式"""

import argparse
import json
import os
import sys
from pathlib import Path


SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
SKILLS_PATH = str(SKILLS_DIR)


def generate_skill_json(name: str, description: str, author: str, params: dict, mcp: bool = False) -> dict:
    """生成 skill.json 内容"""
    skill = {
        "name": name,
        "version": "1.0.0",
        "description": description,
        "author": author,
        "entrypoint": "scripts/main.py",
        "schema": {},
    }
    if params:
        skill["schema"] = {"params": params}
    if mcp:
        skill["invoke"] = "stdin"
    return skill


def generate_skill_md(name: str, description: str, params: dict, mcp: bool = False) -> str:
    """生成 SKILL.md 内容，含保护性注释和 MCP/CLI 两种调用示例"""
    lines = [f"# {name}", "", description, ""]

    # ── 参数表 ──
    if params:
        lines.append("## 参数")
        lines.append("")
        lines.append("| 参数 | 类型 | 默认值 | 说明 |")
        lines.append("|------|------|--------|------|")
        for pname, pinfo in params.items():
            ptype = pinfo.get("type", "str")
            pdesc = pinfo.get("description", "")
            pdefault = pinfo.get("default", "")
            lines.append(f"| `{pname}` | {ptype} | {pdefault} | {pdesc} |")
        lines.append("")

    # ── 调用方式 ──
    lines.append("## 调用方式")
    lines.append("")

    script_path = f"{SKILLS_PATH}/{name}/scripts/main.py"

    if mcp:
        lines.append("### MCP stdin 管道（推荐）")
        lines.append("")
        lines.append("```bash")
        lines.append(f"# 初始化连接")
        lines.append(f"echo '{{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\"}}' | python3 {script_path}")
        lines.append("")
        lines.append(f"# 列出可用工具")
        lines.append(f"echo '{{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\"}}' | python3 {script_path}")
        lines.append("")
        lines.append(f"# 调用工具（示例）")
        lines.append(f"echo '{{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{{\"name\":\"<tool_name>\",\"arguments\":{{...}}}}}}' | python3 {script_path}")
        lines.append("```")
        lines.append("")

    lines.append("### CLI 命令行")
    lines.append("")
    if params:
        args_place = " ".join(f"--{pname} <{pname}>" for pname in params)
        lines.append("```bash")
        lines.append(f"python3 {script_path} {args_place}")
        lines.append("```")
    else:
        lines.append("```bash")
        lines.append(f"python3 {script_path}")
        lines.append("```")
    lines.append("")

    # ── 示例 ──
    lines.append("## 示例")
    lines.append("")

    if mcp and params:
        lines.append(f"```bash")
        lines.append(f"# 加密示例")
        lines.append(f"echo '{{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{{\"name\":\"<tool>\",\"arguments\":{{...}}}}}}' | python3 {script_path}")
        lines.append("```")
        lines.append("")

    if params:
        example_args = []
        for pname, pinfo in params.items():
            default = pinfo.get("default", "")
            ptype = pinfo.get("type", "str")
            if ptype in ("bool", "boolean"):
                if default in (True, "true", "True"):
                    example_args.append(f"--{pname}")
            else:
                val = default if default else f"<{pname}>"
                example_args.append(f"--{pname} {val}")
        example_cmd = f"python3 {script_path} {' '.join(example_args)}"
    else:
        example_cmd = f"python3 {script_path}"

    lines.append("```bash")
    lines.append(example_cmd)
    lines.append("```")
    lines.append("")

    # ── 文件结构 ──
    lines.append("## 文件结构")
    lines.append("")
    lines.append(f"- `skills/{name}/skill.json` — 元数据与参数 Schema")
    lines.append(f"- `skills/{name}/SKILL.md` — skill 说明文档")
    lines.append(f"- `skills/{name}/scripts/main.py` — skill 主程序")
    return "\n".join(lines) + "\n"


def generate_main_py(name: str, params: dict, mcp: bool = False) -> str:
    """生成 scripts/main.py 模板，MCP 模式生成 stdio JSON-RPC 服务端骨架"""

    if mcp:
        return _generate_mcp_main_py(name, params)
    else:
        return _generate_cli_main_py(name, params)


def _generate_cli_main_py(name: str, params: dict) -> str:
    """生成 CLI 模式的 main.py 模板"""
    has_params = bool(params)
    lines = [
        f'#!/usr/bin/env python3',
        f'"""{name} skill"""',
        f'',
    ]
    if has_params:
        lines += [
            'import argparse',
            'import json',
            'import sys',
            '',
            '',
            'def main():',
            f'    parser = argparse.ArgumentParser(description="{name} skill")',
        ]
        for pname, pinfo in params.items():
            ptype = pinfo.get("type", "str")
            pdefault = pinfo.get("default", None)
            pdesc = pinfo.get("description", "")
            if ptype in ("bool", "boolean"):
                action = "store_false" if pdefault in (True, "true", "True", 1) else "store_true"
                lines.append(f'    parser.add_argument("--{pname}", action="{action}", help="{pdesc}")')
            else:
                lines.append(f'    parser.add_argument("--{pname}", type={ptype}, default={json.dumps(pdefault)}, help="{pdesc}")')
        lines += [
            '    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")',
            '    args = parser.parse_args()',
            '',
            '    # TODO: 在此编写 skill 核心逻辑',
            f'    result = {{"status": "ok", "message": "Hello from {name}!"}}',
            '',
            '    if args.json:',
            '        print(json.dumps(result, ensure_ascii=False, indent=2))',
            '    else:',
            '        print(result["message"])',
            '',
            '    return 0',
            '',
            '',
            'if __name__ == "__main__":',
            '    sys.exit(main())',
        ]
    else:
        lines += [
            'import json',
            'import sys',
            '',
            '',
            'def main():',
            '    # TODO: 在此编写 skill 核心逻辑',
            f'    result = {{"status": "ok", "message": "Hello from {name}!"}}',
            '',
            '    print(json.dumps(result, ensure_ascii=False, indent=2))',
            '    return 0',
            '',
            '',
            'if __name__ == "__main__":',
            '    sys.exit(main())',
        ]
    return "\n".join(lines) + "\n"


def _generate_mcp_main_py(name: str, params: dict) -> str:
    """生成 MCP stdio 模式的 main.py 模板，含 JSON-RPC 协议骨架"""
    has_params = bool(params)

    # 构造 tool 参数属性
    param_props_lines = []
    param_required = []
    if has_params:
        for pname, pinfo in params.items():
            ptype = pinfo.get("type", "str")
            pdesc = pinfo.get("description", "")
            pdefault = pinfo.get("default", None)
            def_str = f'"default": {json.dumps(pdefault)}, ' if pdefault is not None else ''
            param_props_lines.append(f'                "{pname}": {{"type": "{ptype}", {def_str}"description": "{pdesc}"}}')
            # 没有 default 的参数视为必填
            if pdefault is None or pdefault == "":
                param_required.append(f'"{pname}"')

    props_block = ",\n".join(param_props_lines) if param_props_lines else ""
    required_block = ", ".join(param_required) if param_required else ""

    # 参数取值代码
    if has_params:
        get_args_lines = []
        for pname, pinfo in params.items():
            pdefault = pinfo.get("default", "None")
            if isinstance(pdefault, str):
                pdefault = f'"{pdefault}"'
            get_args_lines.append(f'    {pname} = args.get("{pname}", {pdefault})')
        get_args_block = "\n".join(get_args_lines)
    else:
        get_args_block = "    pass  # 无参数"

    template = f'''#!/usr/bin/env python3
"""{name} skill —— MCP stdio JSON-RPC 服务"""


import json
import sys


# ============================================================
# ============================================================

def handle_tool_call(tool_name: str, arguments: dict) -> str:
    """处理 tools/call 请求，返回结果字符串。
    
    """
{get_args_block}

    # TODO: 在此实现具体工具逻辑
    if tool_name == "example":
        return f"Hello from {name}!"
    else:
        raise ValueError(f"Unknown tool: {{tool_name}}")


# ============================================================
# ============================================================

def handler(req: dict) -> dict:
    mid = req.get("id")
    method = req.get("method", "")

    if method == "initialize":
        return {{
            "jsonrpc": "2.0",
            "id": mid,
            "result": {{
                "protocolVersion": "2024-11-05",
                "serverInfo": {{"name": "{name}", "version": "1.0.0"}},
                "capabilities": {{"tools": {{}}}}
            }}
        }}

    if method == "tools/list":
        return {{
            "jsonrpc": "2.0",
            "id": mid,
            "result": {{
                "tools": [
                    {{
                        "name": "example",
                        "description": "{name} skill 示例工具",
                        "inputSchema": {{
                            "type": "object",
                            "properties": {{
{props_block}
                            }},
                            "required": [{required_block}]
                        }}
                    }}
                ]
            }}
        }}

    if method == "tools/call":
        params = req.get("params", {{}})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {{}})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = {{}}
        try:
            result_text = handle_tool_call(tool_name, arguments)
        except Exception as e:
            return {{
                "jsonrpc": "2.0",
                "id": mid,
                "error": {{"code": -32000, "message": str(e)}}
            }}
        return {{
            "jsonrpc": "2.0",
            "id": mid,
            "result": {{"content": [{{"type": "text", "text": result_text}}]}}
        }}

    return {{
        "jsonrpc": "2.0",
        "id": mid,
        "error": {{"code": -32601, "message": f"Unknown method: {{method}}"}}
    }}


if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    if not raw:
        sys.exit(0)
    try:
        req = json.loads(raw)
    except json.JSONDecodeError:
        req = json.loads(raw.replace("\\n", "").replace("\\r", ""))
    resp = handler(req)
    sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\\n")
'''
    return template


def create_skill(name: str, description: str, author: str, params_str: str, mcp: bool = False) -> dict:
    """创建 skill 目录和所有文件"""
    # 解析 params JSON 并验证格式
    params = {}
    if params_str and params_str.strip():
        try:
            params = json.loads(params_str)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"params JSON 解析失败: {e}"}
        if isinstance(params, dict):
            for pname, pinfo in params.items():
                if not isinstance(pinfo, dict):
                    return {"success": False, "error": f"参数 '{pname}' 的值必须是对象（含 type/description），当前为: {type(pinfo).__name__}"}

    # 验证 name
    if not name or not name.strip():
        return {"success": False, "error": "name 不能为空"}
    name = name.strip().lower().replace(" ", "-")

    skill_dir = SKILLS_DIR / name
    if skill_dir.exists():
        return {"success": False, "error": f"skill 目录已存在: {skill_dir}"}

    # 创建目录
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # 写入文件
    files = {
        skill_dir / "skill.json": json.dumps(
            generate_skill_json(name, description, author, params, mcp),
            ensure_ascii=False, indent=2
        ) + "\n",
        skill_dir / "SKILL.md": generate_skill_md(name, description, params, mcp),
        scripts_dir / "main.py": generate_main_py(name, params, mcp),
    }

    for path, content in files.items():
        path.write_text(content, encoding="utf-8")

    # 设置可执行权限
    (scripts_dir / "main.py").chmod(0o755)

    return {
        "success": True,
        "skill_dir": str(skill_dir),
        "mcp": mcp,
        "files": [str(p.relative_to(SKILLS_DIR)) for p in files],
    }


def main():
    parser = argparse.ArgumentParser(description="创建新的 skill（CLI / MCP stdio）")
    parser.add_argument("--name", type=str, required=True, help="skill 名称")
    parser.add_argument("--description", type=str, default="", help="skill 描述")
    parser.add_argument("--author", type=str, default="agent", help="作者")
    parser.add_argument("--params", type=str, default="", help="JSON 格式的参数 Schema")
    parser.add_argument("--mcp", action="store_true", help="创建 MCP stdio 模式的 skill")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    args = parser.parse_args()

    result = create_skill(args.name, args.description, args.author, args.params, args.mcp)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            mode = "MCP stdio" if args.mcp else "CLI"
            print(f"✅ skill 创建成功（{mode} 模式）")
            print(f"   目录: {result['skill_dir']}")
            for f in result["files"]:
                print(f"   ✓ {f}")
        else:
            print(f"❌ 创建失败: {result['error']}")

    return 0 if result["success"] else 1
if __name__ == "__main__":

    sys.exit(main())
