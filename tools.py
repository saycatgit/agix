"""工具注册表: OpenAI function calling 格式的工具定义 + 系统提示词"""

import os, sys, threading , re, subprocess, json
from prompt_toolkit import prompt as _prompt


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建或覆写文件，支持追加模式分批写入大文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件相对路径，必须填写"},
                    "content": {"type": "string", "description": "文件内容，必须填写，单次写入超过 10240 字符时应分批调用 write_file  append=true 追加写入"},
                    "append": {"type": "boolean", "description": "是否追加模式，必须填写，true 时在文件末尾追加内容，false 时覆写"}
                },
                "required": ["path", "content", "append"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_patch",
            "description": "通过 unified diff 格式的 patch 文本精确修改文件。使用 ---/+++ 和 @@ 标记定位文件与行号，空格行是上下文匹配锚点，- 开头删除，+ 开头新增。上下文精确匹配时才应用，否则返回错误提示。适合小范围精确代码编辑，比整文件覆写更安全。",
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "unified diff 格式的 patch 文本"
                    }
                },
                "required": ["input"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容，可指定起始行和行数，默认读取全部",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件相对路径，必须填写"},
                    "offset": {"type": "integer", "description": "起始行号（从1开始）"},
                    "limit": {"type": "integer", "description": "读取行数"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "执行 Shell 命令，可用于编译、测试、构建等命令行操作",
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
                    }
                },
                "required": ["command"]
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
            "description": "启动任务模式：将对话中的需求转化为正式任务，进入完整的规划→分解→执行流程。当用户明确要求执行开发、调试、分析等具体任务时调用。可设置立即执行或延期执行或定时执行",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "要执行的任务描述，应清晰完整地表达任务目标"}
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "标记任务完成。任务执行完毕后必须调用此函数。",
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
]



class ToolExecutor:
    """工具执行器：将 tool_call 转换为实际操作"""

    def __init__(self, work_dir: str, logger=None, agent=None):
        self.work_dir = os.path.abspath(work_dir)
        self.logger = logger
        self.agent = agent

    # 各工具必填参数
    _REQUIRED_ARGS = {
        "file_patch": ["input"],
        "write_file": ["path", "content", "append"],
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
            # finish 返回 dict 供 _run_loop 判断，不能转字符串
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
        path = os.path.join(self.work_dir, args["path"])
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        append_mode = args.get("append", False)
        content = args.get("content", "")
        # 非追加模式单次写入不超过 10000 字符
        MAX_WRITE_CHARS = 10000
        if not append_mode and len(content) > MAX_WRITE_CHARS:
            return (
                f"write_file 单次写入内容超过 {MAX_WRITE_CHARS} 字符（当前 {len(content)} 字符）。"
                f" 请分批写入：先用 write_file(append=false) 写入前半部分，再用 write_file(append=true) 分批追加剩余内容。"
            )
        mode = "a" if append_mode else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(args["content"])
        action = "追加" if append_mode else "写入"
        return f"已{action} {path} ({len(args['content'])} 字符)"

    def _tool_read_file(self, args: dict) -> str:
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
        if len(content) > 5000:
            content = content[:5000] + "\n...(已截断)"
        if limit:
            return f"(共{total}行, 读取第{start+1}-{end}行)\n{content}"
        else:
            return f"(共{total}行)\n{content}"

    def _tool_run_shell(self, args: dict) -> str:
        try:
            r = subprocess.run(
                args["command"],
                shell=True,
                cwd=args.get("workdir", self.work_dir),
                capture_output=True,
                text=True,
                timeout=args.get("timeout", 30)
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

    def _tool_start_task(self, args: dict) -> str:
        """将任务提交到调度器，由工作线程统一执行（立即或定时）"""
        task = args.get("task", "")
        if not task:
            return "start_task 需要 task 参数"
        if not self.agent:
            return "start_task 不可用：未关联 agent 实例"
        if getattr(self.agent, '_in_task_mode', False):
            return "start_task 不可用：已在任务模式中，不能嵌套启动"

        first_time = args.get("first_execution_time", "") or "now"
        is_periodic = args.get("is_periodic", False)
        period = args.get("period", "")

        r = self.agent.scheduler.add_task(task, first_time, is_periodic=is_periodic, period=period)
        if r["ok"]:
            is_now = (not first_time or
                      first_time.strip().lower() in ("now", "immediate", "立即"))
            prefix = "任务已提交成功（立即执行）" if is_now else "任务已成功加入待执行列表"
            msg = (f"{prefix}:\n"
                   f"  ID: {r['task']['id']}\n"
                   f"  任务: {task[:80]}\n"
                   f"  下次执行: {r['task']['next_execution_time']}"
                   f"{' (周期: ' + period + ')' if is_periodic else ''}"
                   f"\n任务提交成功，任务结束，立刻调用finish结束会话。")
            if self.logger:
                self.logger.log(msg, always=True)
            return msg
        else:
            msg = f"添加任务失败: {r['error']}"
            if self.logger:
                self.logger.log(msg, always=True)
            return msg


    def _tool_ask_user(self, args: dict) -> str:
        """向用户提问并获取输入，返回用户回答或错误信息。"""
        question = args.get("question", "")
        if not question:
            return "ask_user 需要 question 参数"

        # 检查是否在 worker 线程（非主线程），拒绝读取 stdin
        if threading.current_thread() is not threading.main_thread():
            return (
                f"无法获取用户输入: 后台任务不支持交互式输入。\n"
                f"原问题: {question}"
            )

        # 检查是否为交互式终端
        if not sys.stdin.isatty():
            return (
                f"无法获取用户输入: 当前运行环境不支持交互式输入（非 TTY）。\n"
                f"原问题: {question}"
            )

        # 输出问题（统一用 logger 或 print）
        self._log_message(f"\033[96m❓ {question}\033[0m")

        # 获取用户输入，优先使用 prompt_toolkit（提供更好的交互体验）
        try:
            # 尝试导入 prompt_toolkit（作为可选依赖）
            answer = _prompt("   > ").strip()
        except ImportError:
            # fallback 到标准 input
            try:
                answer = input("   > ").strip()
            except (EOFError, KeyboardInterrupt):
                answer = None
        except (EOFError, KeyboardInterrupt):
            answer = None
        except Exception as e:
            # 捕获其他意外异常（如 IOError）
            self._log_message(f"获取用户输入时发生异常: {e}")
            return f"获取用户输入失败: {e}"

        # 输出空行分隔
        self._log_message("")

        if answer is None:
            return "用户取消了输入"
        if answer == "":
            return "用户未提供回答（空输入）"
        return f"用户回答: {answer}"

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
        return os.path.join(self.work_dir, file_path)

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
            self.logger.log(msg, always=True)
        else:
            print(msg)

    def _tool_finish(self, args: dict) -> dict:
        """特殊工具：返回 dict 而非 str，由调用方处理"""
        return {"type": "finish", "success": args["success"], "summary": args["summary"]}


