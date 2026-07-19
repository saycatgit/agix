from meta import MsgStyle
from utils import Utils
"""工具注册表: OpenAI function calling 格式的工具定义 + 系统提示词"""

import os, sys, threading , re, subprocess, json


def get_tools_excluding(*names: str) -> list:
    """返回排除指定工具后的 TOOLS 列表。"""
    return [t for t in TOOLS if t["function"]["name"] not in names]


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": ("创建或覆写文件，支持追加模式分批写入大文件,先判断要写入内容大小再决定是否分批写,单次不超过10000字节"),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件相对路径，必须填写."},
                    "content": {"type": "string", "description": "文件内容，必须填写."},
                    "append": {"type": "boolean", "description": "是否追加模式，true 时在文件末尾追加内容，false 时覆写,默认false."},
                    "note": {"type": "string", "description": "简要描述思考过程和调用这个工具的原因50字以内，用于提示用户当前状况及进度"}
                },
                "required": ["path", "content","note"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_patch",
            "description": ("通过 unified diff 格式的 patch 文本精确修改文件。"
                            "使用 ---/+++ 和 @@ 标记定位文件与行号，空格行是上下文匹配锚点，- 开头删除，+ 开头新增。patch 头 `--- a/` 和 `+++ b/` 后的路径支持相对路径和绝对路径，建议始终使用绝对路径，避免工作目录不同导致相对路径解析到错误位置。上下文精确匹配时才应用，否则返回错误提示。适合小范围精确代码编辑，比整文件覆写更安全。"
                            "关键规则：每行的第1列是指令前缀（空格=保持, -=删除, +=新增），第2列起是文件原文（缩进必须和 read_file 看到的一模一样）。"
                            "例如 read_file 返回 `    home = '~'`（4空格缩进），diff 中应写作 `     home = '~'`（1前缀空格 + 4缩进空格 = 5空格）。"
                            "常见错误：漏掉前缀列占的那一个空格，导致 diff 里的缩进比原文少1格，上下文匹配失败。"
                            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "unified diff 格式的 patch 文本"
                    },
                    "note": {"type": "string", "description": "简要描述思考过程和调用这个工具的原因50字以内，用于提示用户当前状况及进度"}
                },
                "required": ["input","note"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": ("读取文件内容，可指定起始行和行数，默认读取全部"),

            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件相对路径，必须填写"},
                    "offset": {"type": "integer", "description": "起始行号（从1开始）"},
                    "limit": {"type": "integer", "description": "读取行数"},
                    "note": {"type": "string", "description": "简要描述思考过程和调用这个工具的原因50字以内，用于提示用户当前状况及进度"}

                },
                "required": ["path","note"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": ("执行 Shell 命令，可用于编译、测试、构建等命令行操作"),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 Shell 命令，必须填写"
                    },
                    "workdir": {
                        "type": "string",
                        "description": "工作目录，默认项目根目录"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数，默认 30秒"
                    },
                    "note": {"type": "string", "description": "简要描述思考过程和调用这个工具的原因50字以内，用于提示用户当前状况及进度"}

                },
                "required": ["command","note"]
            }
        }
    },
    
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "向用户提问并等待回答。在需要用户决策、澄清需求、\\n"
                "或遇到无法自动判断的问题时调用此工具。\\n"
                "工具会阻塞等待用户输入，然后将用户回答返回给 LLM。\\n"
                "仅在必要时使用，不要频繁打断用户。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "向用户提出的问题"
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_task",
            "description": (
                "启动任务模式：将对话中的需求转化为正式任务，进入完整的规划→分解→执行流程。"
                "可设置立即执行、延期执行、定时执行，也可以设置是否为交互模式，如果是立即执行的任务默认为交互。"
                "调用完start_task后，必须调用finish工具结束任务，禁止继续执行。"
                ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "要执行的任务描述，应清晰完整地表达任务目标"},
                    "first_execution_time": {"type": "string", "description": "首次执行时间。ISO格式如2026-07-08T20:00:00，或相对时间如+10m/+2h/+1d，默认为now立即执行"},
                    "is_periodic": {"type": "boolean", "description": "是否周期性任务，默认false"},
                    "period": {"type": "string", "description": "周期间隔，如1d/12h/30m/1w。仅is_periodic为true时需要"},
                    "interactive": {"type": "boolean", "description": "是否为交互模式任务，默认false"}
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": ("标记任务完成。会话结束,或者任务已经提交必须调用此工具。"),

            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "description": "任务是否成功完成"},
                    "summary": {"type": "string", "description": "任务完成情况全面总结"}
                },
                "required": ["success", "summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_plan",
            "description": ("更新当前子任务的阶段执行计划。用于在每个阶段开始时规划详细步骤，或执行过程中更新步骤状态。如果是任务模式，部分stage 来源为 spec.json 中的 phase_name，如果是chat模式，stage为llm自己规划，step 来源为 LLM，status 取值为 pending/in_progress/completed/failed。同一阶段中同时只有一个步骤处于 in_progress。"),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "description": "步骤列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step": {"type": "string", "description": "步骤描述"},
                                "status": {"type": "string", "description": "步骤状态: pending|in_progress|completed|failed"}
                            },
                            "required": ["step", "status"]
                        }
                    },
                    "stage": {"type": "string", "description": "指定更新哪个阶段（phase_name），如'需求分析'"},
                    "explanation": {"type": "string", "description": "本次更新说明，选填"}
                },
                "required": ["steps", "stage"]
            }
        }
    },
]


class ToolExecutor:
    """工具执行器：将 tool_call 转换为实际操作"""

    def __init__(self, work_dir: str, logger=None, agent=None, eqm=None, mode: str = "chat"):
        self.work_dir = os.path.abspath(work_dir)
        self.eqm = eqm            # EventQueueManager
        self.mode = mode          # "chat" | "task"
        self.logger = logger
        self.agent = agent

    # 各工具必填参数
    _REQUIRED_ARGS = {
        "file_patch": ["input"],
        "update_plan": ["steps", "stage"],
        "write_file": ["path", "content"],
        "read_file": ["path"],
        "run_shell": ["command"],
        "ask_user": ["question"],
        "start_task": ["task"],
        "finish": ["success", "summary"],
    }

    def execute(self, name: str, args: dict) -> str:
        """执行单个工具调用，返回结果字符串"""
        method = getattr(self, f"_tool_{name}", None)
        if method is None:
            return f"未知工具: {name}"

        # 检查必填参数
        required = self._REQUIRED_ARGS.get(name, [])
        missing = [p for p in required if p not in args or args.get(p, "") == ""]
        if missing:
            msg = f"调用 {name} 缺少必填参数: {', '.join(missing)}。"
            msg += f" 该工具需要: {', '.join(required)}。"
            msg += f" 实际传入: {json.dumps(args, ensure_ascii=False)}。"
            msg += f" 请在下一轮重新调用，确保所有必填参数都已提供。"
            return msg

        try:
            result = method(args)
            tool_msg = f"{str(args.get('note','')).replace(chr(10),' ')} ({name}: {str(args)[9:100].replace(chr(10),' ')})"
            if self.agent and self.agent.eqm:
                mode = self.mode
                self.agent.eqm.send_display(tool_msg, mode=mode, style=MsgStyle.ACTION)
            if isinstance(result, dict) and result.get("type") == "finish":
                return result
            return str(result)
        except KeyError as e:
            msg = f"调用 {name} 缺少参数 '{e.args[0]}'。"
            msg += f" 该工具需要: {', '.join(required)}。"
            msg += f" 实际传入: {json.dumps(args, ensure_ascii=False)}。"
            msg += f" 请在下一轮重新调用，提供完整参数。"
            return msg
        except Exception as e:
            return f"执行 {name} 失败: {e}"


    def _tool_write_file(self, args: dict) -> str:

        if os.path.isabs(args["path"]):
            path = args["path"]
        else:
            path = os.path.join(self.work_dir, args["path"])

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        append_mode = args.get("append", False)
        content = args.get("content", "")
        # 单次写入不超过 10000 字符（append=true 也限制）
        MAX_WRITE_CHARS = 10000
        if len(content) > MAX_WRITE_CHARS:
            return (
                f"write_file 单次写入内容超过 {MAX_WRITE_CHARS} 字符（当前 {len(content)} 字符），"
                f"请分批写入：每次 write_file 的 content 不超过 {MAX_WRITE_CHARS} 字符，用 append=true 从第二批开始逐批追加。"
            )
        mode = "a" if append_mode else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(args["content"])
        action = "追加" if append_mode else "写入"
        return f"已{action} {path} ({len(args['content'])} 字符)"

    def _tool_read_file(self, args: dict) -> str:

        if os.path.isabs(args["path"]):
            path = args["path"]
        else:
            path = os.path.join(self.work_dir, args["path"])

        if not os.path.exists(path):
            return f"文件不存在: {path}"
        offset = args.get("offset", 1)
        limit = args.get("limit")
        with open(path, "r", encoding="utf-8") as f:
            lines_data = f.readlines()
        total = len(lines_data)
        start = max(0, offset - 1)
        end = min(total, start + limit) if limit else total
        selected = lines_data[start:end]
        content = "".join(selected)
        if limit:
            return f"(共{total}行, 读取第{start+1}-{end}行)\n{content}"
        else:
            return f"(共{total}行)\n{content}"

    def _tool_run_shell(self, args: dict) -> str:
        command = args["command"]
        cwd = args.get("workdir", self.work_dir)
        timeout = args.get("timeout", 30)

        # 检测 sudo 命令，智能获取密码
        needs_sudo = bool(re.search(r'\bsudo\b', command))
        sudo_password = None
        if needs_sudo:
            sudo_password = self._resolve_sudo_password(command,note=args.get("note"))
            if sudo_password is None:
                return "用户取消 sudo 密码输入，命令未执行"
            command = re.sub(r'(^|\s)sudo\b', r'\1sudo -S', command)

        try:
            r = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                input=(sudo_password + '\n') if sudo_password else None,
                timeout=timeout,
            )
            out = r.stdout.strip()
            err = r.stderr.strip()
            parts = []
            if out:
                parts.append(out)
            if err:
                parts.append(f"[stderr] {err}")
            parts.append(f"(exit={r.returncode})")
            return "\n".join(parts)
        except subprocess.TimeoutExpired:
            return "命令超时"

    def _resolve_sudo_password(self, command: str, note: str = ""):
        """获取 sudo 密码：先查内存缓存，有则确认，无则输入。"""
        agent = getattr(self, "agent", None)
        if agent and not getattr(agent, "is_interactive", False):
            # 非交互模式：有缓存密码直接用，没有返回 None
            if agent.config and agent.config.sudo_password:
                return agent.config.sudo_password
            return None

        config = agent.config if agent else None
        Utils.play_notification()

        if config and config.sudo_password:
            eqm = getattr(self, "eqm", None)
            if eqm is not None:
                answer = eqm.ask_for_confirmation(
                    note+"\n是否使用已保存的 sudo 密码？",
                    mode=getattr(self, "mode", "chat"),
                )
                if answer.strip() in ("是", "yes", "y", "1"):
                    return config.sudo_password
            # 用户选了"否"，继续要求输入

        eqm = getattr(self, "eqm", None)
        if eqm is not None:
            password = eqm.ask_for_password(
                note+"\n请输入 sudo 密码",
                mode=getattr(self, "mode", "chat"),
            )
            if not password or not password.strip():
                return None
            if config is not None:
                config.sudo_password = password
            return password
        return None

    def _tool_start_task(self, args: dict) -> str:
        """将任务提交到调度器，由工作线程统一执行（立即或定时）"""
        task = args.get("task", "")
        if not task:
            return "start_task 需要 task 参数"
        if not self.agent:
            return "start_task 不可用：未关联 agent 实例"
        if self.mode == "task":
            return "start_task 不可用：已在任务模式中，不能嵌套启动"

        first_time = args.get("first_execution_time", "") or "now"
        is_periodic = args.get("is_periodic", False)
        period = args.get("period", "")
        is_now = (not first_time or
                  first_time.strip().lower() in ("now", "immediate", "立即"))
        # 立即执行的任务默认启用交互模式
        is_interactive = args.get("interactive", False) or is_now

        r = self.agent.scheduler.add_task(task, first_time, is_periodic=is_periodic, period=period, is_interactive=is_interactive)
        if r["ok"]:
            prefix = "任务已提交成功（立即执行）" if is_now else "任务已成功加入待执行列表"
            msg = (f"{prefix}:\n"
                   f"  ID: {r['task']['id']}\n"
                   f"  任务: {task[:80]}\n"
                   f"  下次执行: {r['task']['next_execution_time']}"
                   f"{' (周期: ' + period + ')' if is_periodic else ''}"
                   f"\n任务提交成功，任务结束。")
            if self.logger:
                self.logger.log(msg)
            return msg
        else:
            msg = f"添加任务失败: {r['error']}"
            if self.logger:
                self.logger.log(msg)
            return msg


    def _tool_ask_user(self, args: dict) -> str:
        """向用户提问并获取输入，返回用户回答或错误信息。"""
        question = str(args.get("question", "") or "")
        if not question.strip():
            return "ask_user 需要 question 参数"

        Utils.play_notification()

        # 优先使用 EventQueueManager 进行交互
        eqm = getattr(self, "eqm", None)
        # 非交互模式直接拒绝，不管有没有 eqm
        if self.agent and not getattr(self.agent, "is_interactive", False):
            return f"无法获取用户输入: 当前任务不是交互模式。\n原问题: {question}"

        if eqm is not None:
            return eqm.ask_user(question, mode=getattr(self, "mode", "chat"))

        # 回退: 无 eqm 时返回错误提示
        return f"无法获取用户输入: 交互界面不可用。\n原问题: {question}"

    def _tool_file_patch(self, args: dict) -> str:
        """通过 unified diff patch 精确修改文件，上下文匹配。"""
        patch_text = args.get("input", "")
        if not patch_text.strip():
            return "file_patch: input 参数为空，请提供 unified diff 格式的 patch 内容"

        file_sections = self._parse_unified_diff(patch_text)
        if not file_sections:
            return ("file_patch: 无法从 input 中解析出有效的 unified diff patch。"
                    "请使用以下格式:\n--- a/path/to/file.py\n+++ b/path/to/file.py\n"
                    "@@ -10,7 +10,7 @@\n context line\n-removed line\n+added line\n context line")

        results = []
        for section in file_sections:
            file_path = self._resolve_path(section["file_path"])
            result = self._apply_hunks_to_file(file_path, section["hunks"])
            results.append(result)

        success_count = sum(1 for r in results if r["success"])
        fail_count = sum(1 for r in results if not r["success"])

        parts = []
        for r in results:
            if r["success"]:
                parts.append(f"  OK {r['file']}: {r['message']}")
            else:
                parts.append(f"  FAIL {r['file']}: {r['message']}")
        return f"file_patch 执行完成: {success_count} 成功, {fail_count} 失败\n" + "\n".join(parts)

    def _parse_unified_diff(self, patch_text: str) -> list:
        """解析 unified diff 格式为文件段列表。"""
        sections = []
        current_file = None
        current_hunks = []
        current_hunk_lines = []
        in_hunk = False

        lines = patch_text.split('\n')
        if lines and lines[-1] == '':
            lines.pop()
        for line in lines:
            if line.startswith('--- '):
                continue
            elif line.startswith('+++ '):
                file_path = line[4:].strip()
                if file_path.startswith('a/') or file_path.startswith('b/'):
                    file_path = file_path[2:]
                current_file = file_path
                current_hunks = []
            elif in_hunk:
                if line.startswith('@@'):
                    if current_hunk_lines:
                        current_hunks.append(self._build_hunk(current_hunk_lines))
                    current_hunk_lines = [line]
                elif (line.startswith(' ') or line.startswith('-') or
                      line.startswith('+') or line.startswith('\\')):
                    current_hunk_lines.append(line)
                elif line.strip() == '':
                    current_hunk_lines.append(line)
                else:
                    if current_hunk_lines:
                        current_hunks.append(self._build_hunk(current_hunk_lines))
                        current_hunk_lines = []
                    if current_file:
                        sections.append({"file_path": current_file, "hunks": current_hunks})
                    current_file = None
                    current_hunks = []
                    in_hunk = False
            elif line.startswith('@@ '):
                in_hunk = True
                current_hunk_lines = [line]

        if current_hunk_lines:
            current_hunks.append(self._build_hunk(current_hunk_lines))
        if current_file and current_hunks:
            sections.append({"file_path": current_file, "hunks": current_hunks})
        return sections

    def _build_hunk(self, lines: list) -> dict:
        """从 @@ header + 行列表构建 hunk 结构。"""
        header_line = lines[0]
        m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$', header_line)
        if not m:
            raise ValueError(f"Invalid hunk header: {header_line}")
        old_start = int(m.group(1))
        old_count = int(m.group(2)) if m.group(2) else 1
        new_start = int(m.group(3))
        new_count = int(m.group(4)) if m.group(4) else 1
        header_comment = m.group(5).strip()

        hunk_lines = []
        for line in lines[1:]:
            prefix = line[0] if line else ' '
            content = line[1:] if line else ''
            hunk_lines.append({"prefix": prefix, "content": content})

        return {
            "old_start": old_start,
            "old_count": old_count,
            "new_start": new_start,
            "new_count": new_count,
            "header": header_comment,
            "lines": hunk_lines
        }

    def _resolve_path(self, file_path: str) -> str:
        """解析文件路径（相对于 work_dir）。"""
        if os.path.isabs(file_path):
            return file_path
        resolved = os.path.join(self.work_dir, file_path)
        if os.path.exists(resolved):
            return resolved
        abs_try = "/" + file_path
        if os.path.exists(abs_try):
            return abs_try
        return resolved

    def _apply_hunks_to_file(self, file_path: str, hunks: list) -> dict:
        """将 hunks 应用到文件，返回结果 dict。"""
        try:
            file_exists = os.path.exists(file_path)
            if file_exists:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            else:
                lines = []

            applied_hunks = 0
            errors = []
            rel_path = os.path.relpath(file_path, self.work_dir)

            for hunk_idx, hunk in enumerate(hunks):
                old_start = hunk["old_start"]
                context_lines = []
                for hl in hunk["lines"]:
                    if hl["prefix"] in (' ', '-'):
                        context_lines.append(hl["content"])

                if not file_exists and not context_lines:
                    # New file with only additions: append all + lines
                    new_lines = []
                    for hl in hunk["lines"]:
                        if hl["prefix"] == '+':
                            line_content = hl["content"]
                            if not line_content.endswith('\n'):
                                line_content += '\n'
                            new_lines.append(line_content)
                    lines.extend(new_lines)
                    applied_hunks += 1
                    continue

                match_pos = self._find_context_match(lines, context_lines, old_start - 1)
                if match_pos is None:
                    match_pos = self._fuzzy_find_context(lines, context_lines)
                if match_pos is None:
                    # 最后尝试：忽略前导空白进行模糊匹配
                    # Agent 生成的 diff 可能缩进有偏差（少/多一个空格），此兜底容忍该问题
                    match_pos = self._fuzzy_find_context_ws(lines, context_lines)

                if match_pos is None:
                    ctx_preview = '\n'.join(context_lines[:3])
                    # 增强错误信息：同时显示文件中对应位置的实际内容
                    pos = old_start - 1
                    extra_hint = ""
                    if 0 <= pos < len(lines):
                        actual_at_pos = ''.join(lines[pos:pos+3]).rstrip()
                        extra_hint = (
                            f"\n  文件中 hunk 起始位置(old_start={old_start})的实际内容(前3行): "
                            f"{repr(actual_at_pos[:200])}"
                        )
                    elif pos >= len(lines):
                        extra_hint = (
                            f"\n  文件中 hunk 起始位置(old_start={old_start})超出文件范围"
                            f"(文件共{len(lines)}行)"
                        )
                    errors.append(
                        f"hunk {hunk_idx + 1}: 无法在 {rel_path} 中找到匹配上下文，"
                        f"预期上下文(前3行): {ctx_preview}{extra_hint}"
                    )
                    continue

                new_lines = []
                for hl in hunk["lines"]:
                    if hl["prefix"] in ('+', ' '):
                        line_content = hl["content"]
                        if not line_content.endswith('\n'):
                            line_content += '\n'
                        new_lines.append(line_content)

                old_hunk_lines = sum(1 for hl in hunk["lines"] if hl["prefix"] in (' ', '-'))
                lines[match_pos:match_pos + old_hunk_lines] = new_lines
                applied_hunks += 1

            if errors:
                return {
                    "success": False,
                    "file": rel_path,
                    "message": "; ".join(errors),
                    "applied": applied_hunks
                }

            dir_path = os.path.dirname(os.path.abspath(file_path)) or "."
            os.makedirs(dir_path, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                for line in lines:
                    f.write(line)

            return {
                "success": True,
                "file": rel_path,
                "message": f"应用了 {applied_hunks} 个 hunk",
                "applied": applied_hunks
            }
        except FileNotFoundError as e:
            return {"success": False, "file": rel_path, "message": f"文件不存在: {e}"}
        except PermissionError as e:
            return {"success": False, "file": rel_path, "message": f"权限不足: {e}"}
        except Exception as e:
            return {"success": False, "file": rel_path, "message": f"异常: {e}"}

    def _find_context_match(self, file_lines: list, context_lines: list, start_pos: int):
        """在指定位置精确匹配上下文行。"""
        if start_pos < 0 or start_pos + len(context_lines) > len(file_lines):
            return None
        for i, ctx_line in enumerate(context_lines):
            file_line = file_lines[start_pos + i].rstrip('\n')
            if file_line != ctx_line:
                return None
        return start_pos

    def _fuzzy_find_context(self, file_lines: list, context_lines: list):
        """全文件搜索匹配上下文位置（精确匹配）。"""
        if not context_lines:
            return None
        for i in range(len(file_lines) - len(context_lines) + 1):
            match = True
            for j, ctx_line in enumerate(context_lines):
                if file_lines[i + j].rstrip('\n') != ctx_line:
                    match = False
                    break
            if match:
                return i
        return None

    def _fuzzy_find_context_ws(self, file_lines: list, context_lines: list):
        """全文件搜索匹配上下文位置（忽略每行前导空白差异）。
        
        Agent 生成的 unified diff 有时会有缩进偏差（少/多一个空格），
        此方法将 context 和 file 的每行都去除前导空白后再比较，
        作为精确匹配失败后的最终兜底。
        
        注意：此匹配较宽松，但只在精确匹配和普通模糊匹配都失败时才启用。
        """
        if not context_lines:
            return None
        # 预处理 context：去掉前导空白
        ctx_stripped = [l.lstrip() for l in context_lines]
        for i in range(len(file_lines) - len(context_lines) + 1):
            match = True
            for j, cs in enumerate(ctx_stripped):
                fl = file_lines[i + j].rstrip('\n').lstrip()
                if fl != cs:
                    match = False
                    break
            if match:
                return i
        return None

    def _log_message(self, msg: str):
        """统一处理日志输出。"""
        if self.logger:
            self.logger.log(msg)
        else:
            print(msg)

    def _tool_update_plan(self, args: dict) -> str:
        """更新阶段执行计划。"""
        steps = args.get("steps", [])
        stage = args.get("stage", "")
        explanation = args.get("explanation", "")

        agent = getattr(self, "agent", None)
        if not agent:
            return json.dumps({"error": "agent not available"}, ensure_ascii=False)

        if self.mode == "chat":
            progress = getattr(agent, "chat_stage_progress", None)
        else:
            progress = getattr(agent.task_manager, "_stage_progress", None)
        if not progress:
            return json.dumps({"error": "no stage progress initialized"}, ensure_ascii=False)

        progress.update_steps(stage, steps)
        try:
            agent.task_manager.save_plan_steps(agent.task_manager._stage_progress)
        except Exception:
            pass

        # 打印更新后的进度
        if self.logger:
            self.logger.log(f"\n{"="*80}\n{progress.format_status()}\n{"="*80}")
        if self.agent and self.agent.eqm:
            self.agent.eqm.send_display(progress.format_status(), mode=self.mode, style=MsgStyle.STATUS)

        result = {
            "stage": stage,
            "explanation": explanation,
            "status": progress.format_status(),
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _tool_finish(self, args: dict) -> dict:
        """特殊工具：返回 dict 而非 str，由调用方处理"""
        Utils.play_notification()
        return {"type": "finish", "success": args["success"], "summary": args["summary"]}
