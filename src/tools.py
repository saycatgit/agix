from meta import MsgStyle
from utils import Utils
"""工具注册表: OpenAI function calling 格式的工具定义 + 系统提示词"""
from planner import Planner

import os , re, subprocess, json

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
            "name": "user_interaction",
            "description": (
                "与用户交互的统一入口。支持两种类型：\\n"
                "1. type='ask'：向用户提问并阻塞等待回答，用于需要用户决策或澄清需求时；\\n"
                "2. type='thinking'：向用户传递思维链，非阻塞，不等待响应。\\n"
                "【thinking 使用规则】\\n"
                "- 每次执行实质性操作（read_file/write_file/run_shell/file_patch）之前，必须先发 thinking 说明接下来要做什么、为什么这样做。\\n"
                "- 收到工具执行结果后，如果结果与预期不符或需要调整方向，立即发 thinking 说明当前判断和下一步思路。\\n"
                "- thinking 内容要信息密集：当前卡在什么问题、打算怎么解决、为什么选这个方案。不要发\"正在分析\"这类空话。\\n"
                "- 宁可多发不要漏发，用户通过 thinking 跟踪你的思考过程，漏发会让用户感觉思路断层。"
             ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "description": "交互参数",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "交互类型: ask(向用户提问并等待回答) 或 thinking(传递思维链，非阻塞)",
                                "enum": ["ask", "thinking"]
                            },
                            "content": {
                                "type": "string",
                                "description": "ask类型时为向用户提出的问题，thinking类型时为思维链"
                            }
                        },
                        "required": ["type", "content"]
                    }
                },
                "required": ["input"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_management",
            "description": (
                "任务管理工具，统一管理任务生命周期。"
                "参数 task 是一个字典："
                "type='start'时 content 为任务描述，启动任务模式，调用后必须结束会话等待用户下一步指令；"
                "type='finish'时 content 为任务总结，success 为是否成功；"
                "type='requirement'时 content 为从用户的消息中提取的新增需求汇总。，如果content为空则返回当前任务已存储的需求"
                "如果是继续开发之前任务或者在开发过程中有需求变化，及时用task_management(type=\"requirement\", content=\"新需求或者需求变更\") 更新用户需求"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "object",
                        "description": "任务管理参数字典",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "操作类型: start(启动任务) | finish(结束任务) | requirement(新增需求汇总)",
                                "enum": ["start", "finish", "requirement"]
                            },
                            "content": {
                                "type": "string",
                                "description": "type=start时为任务描述, type=finish时为任务总结, type=requirement时为需求汇总"
                            },
                            "success": {
                                "type": "boolean",
                                "description": "仅type=finish时有效，任务是否成功完成，默认true"
                            }
                        },
                        "required": ["type", "content"]
                    }
                },
                "required": ["task"]
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

    def __init__(self, agent=None, mode: str = "chat", task_manager=None):
        if task_manager and task_manager.subtask:
            self.work_dir = os.path.abspath(task_manager.subtask.project_path)
        else:
            self.work_dir = os.path.abspath(".")
        self.mode = mode          # "chat" | "task"
        self.agent = agent
        self.eqm = agent.eqm if agent else None
        self.logger = agent.logger if agent else None
        self.task_manager = task_manager
        # self.eqm.send_debug(f"新tool 路径 ：{self.work_dir}")
    # 各工具必填参数
    _REQUIRED_ARGS = {
        "file_patch": ["input"],
        "update_plan": ["steps", "stage"],
        "write_file": ["path", "content"],
        "read_file": ["path"],
        "run_shell": ["command"],
        "user_interaction": ["input"],
        "task_management": ["task"],
    }

    def _format_tool_display(self, name: str, args: dict) -> str:
        """将工具调用格式化为结构化展示信息。
        提取 note 作为主描述，按工具类型提取关键参数作为辅助信息。
        """
        note = str(args.get("note", "")).replace("\n", " ")

        def _trunc(s: str, n: int = 80) -> str:
            s = s.replace("\n", " ")
            return s if len(s) <= n else s[:n] + "…"

        param_str = ""
        if name == "write_file":
            param_str = _trunc(args.get("path", ""))
        elif name == "read_file":
            param_str = _trunc(args.get("path", ""))
        elif name == "run_shell":
            param_str = _trunc(args.get("command", ""))
        elif name == "file_patch":
            inp = args.get("input", "")
            first_line = inp.split("\n")[0] if inp else ""
            param_str = _trunc(first_line)
        elif name == "user_interaction":
            inp = args.get("input", {})
            if isinstance(inp, str):
                try: inp = json.loads(inp)
                except Exception: inp = {}
            param_str = f"{inp.get('type', '?')}: {_trunc(str(inp.get('content', '')), 60)}"
        elif name == "task_management":
            task = args.get("task", {})
            if isinstance(task, str):
                try: task = json.loads(task)
                except Exception: task = {}
            param_str = f"{task.get('type', '?')}: {_trunc(str(task.get('content', '')), 60)}"
        elif name == "update_plan":
            param_str = f"stage={args.get('stage', '?')}"

        if note and param_str:
            return f"{note}  [{name}] {param_str}"
        elif note:
            return f"{note}  [{name}]"
        else:
            return f"[{name}] {param_str}" if param_str else f"[{name}]"

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
            tool_msg = self._format_tool_display(name, args)
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
            if os.name == 'nt':
                return "Windows 不支持 sudo 提权。如需管理员权限，请以管理员身份运行终端（右键 → 以管理员身份运行）。"
            sudo_password = self._resolve_sudo_password(command,note=args.get("note"))
            if sudo_password is None:
                return "用户取消 sudo 密码输入，命令未执行"
            command = re.sub(r'(^|\s)sudo\b', r'\1sudo -S', command)

        # 危险命令检查 (auth.py AuthHandler)
        auth_handler = getattr(self.agent, "auth", None) if self.agent else None
        if auth_handler:
            is_danger, matched_descs = auth_handler.check_dangerous(command)
        else:
            is_danger, matched_descs = False, []
        if is_danger:
            eqm = getattr(self, "eqm", None)
            agent = getattr(self, "agent", None)
            if agent and not agent.config.execution.interactive:
                return f"⚠️ 危险命令已拦截: {'; '.join(matched_descs)}\n命令: {command}\n\n用户已禁止当前操作，请不要再做类似尝试。"
            if eqm is not None:
                answer = eqm.ask_for_confirmation(
                    f"⚠️ 检测到危险命令:\n{command}\n\n匹配模式: {'; '.join(matched_descs)}\n\n是否继续执行？",
                    mode=getattr(self, "mode", "chat"),
                )
                if answer.strip() not in ("是", "yes", "y", "1"):
                    return "用户取消执行危险命令。\n\n用户已禁止当前操作，请不要再做类似尝试。"

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
        if agent and not agent.config.execution.interactive:
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

    def _start_task(self, content: str) -> str:
        """调用 Planner 对任务进行分类拆解并生成任务文件"""
        if not content:
            return "start_task 需要 task 参数，任务描述中应包含时间/周期/交互模式等所有信息"
        if not self.agent:
            return "start_task 不可用：未关联 agent 实例"
        if self.mode == "task":
            return "start_task 不可用：已在任务模式中，不能嵌套启动"

        planner = Planner(self.agent.config, self.agent.logger, eqm=self.eqm)
        r = planner.run(content)
        if r["ok"]:
            n_subtasks = len(r.get("subtasks", []))
            n_files = len(r.get("task_files", []))
            msg = (f"任务规划完成:\n"
                   f"  任务: {content[:100]}\n"
                   f"  子任务数: {n_subtasks}\n"
                   f"  生成文件: {n_files}\n"
                   f"任务提交成功，任务结束。")
            if self.logger:
                self.logger.log(msg)
            return msg
        else:
            msg = f"添加任务失败: {r['error']}"
            if self.logger:
                self.logger.log(msg)
            return msg


    def _tool_user_interaction(self, args: dict) -> str:
        """与用户交互：type='ask' 阻塞提问，type='thinking' 非阻塞传递思维链/进度。"""
        input_data = args.get("input", {})
        if isinstance(input_data, str):
            try:
                input_data = json.loads(input_data)
            except json.JSONDecodeError:
                return "user_interaction 需要 input 字典，格式: {\"type\": \"ask\"|\"thinking\", \"content\": \"...\"}"

        interaction_type = input_data.get("type", "")
        content = str(input_data.get("content", "") or "")

        if interaction_type == "thinking":
            eqm = getattr(self, "eqm", None)
            if eqm is not None:
                eqm.send_thinking(content, mode=getattr(self, "mode", "chat"))
            return "thinking 已发送"

        if interaction_type == "ask":
            if not content.strip():
                return "user_interaction: ask 类型需要 content 参数"

            Utils.play_notification()

            eqm = getattr(self, "eqm", None)
            if self.agent and not self.agent.config.execution.interactive:
                return f"无法获取用户输入: 当前任务不是交互模式。\n原问题: {content}"

            if eqm is not None:
                tm = getattr(self, "task_manager", None)
                if tm is not None and hasattr(tm, "add_conversation_entry"):
                    tm.add_conversation_entry("assistant", content)
                    answer = eqm.ask_user(content, mode=getattr(self, "mode", "chat"))
                    tm.add_conversation_entry("user", answer)
                    return answer
                return eqm.ask_user(content, mode=getattr(self, "mode", "chat"))

            return f"无法获取用户输入: 交互界面不可用。\n原问题: {content}"

        return f"user_interaction: 未知 type '{interaction_type}'，支持 ask 和 thinking"

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

        if not self.task_manager:
            return json.dumps({"error": "no stage progress initialized"}, ensure_ascii=False)

        progress = self.task_manager._stage_progress
        if not progress:
            return json.dumps({"error": "no stage progress initialized"}, ensure_ascii=False)

        progress.update_steps(stage, steps)
        self.task_manager.save_plan_steps(progress)

        # 打印更新后的进度
        if self.logger:
            sep = "=" * 80
            self.logger.log(f"\n{sep}\n{progress.format_status()}\n{sep}")
        if self.agent and self.agent.eqm:
            self.agent.eqm.send_display(progress.format_status(), mode=self.mode, style=MsgStyle.STATUS)

        result = {
            "stage": stage,
            "explanation": explanation,
            "status": progress.format_status(),
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _tool_task_management(self, args: dict):
        """统一任务管理：type=start|finish|requirement"""
        task = args.get("task", {})
        if isinstance(task, str):
            task = json.loads(task)
        t = task.get("type", "")
        content = task.get("content", "")

        if t == "start":
            # self.eqm.send_debug("start task"+content)

            return self._start_task(content)
        elif t == "finish":
            Utils.play_notification()
            # self.eqm.send_debug("finish task"+content)

            return {"type": "finish", "success": task.get("success", True), "summary": content}
        elif t == "requirement":
            if not content:
                if self.task_manager and hasattr(self.task_manager, '_subtask') and self.task_manager._subtask:
                    return self.task_manager._subtask.sub_task_detail or "(无任务描述)"
                return "(当前无活跃任务)"
            else:
                if self.task_manager and hasattr(self.task_manager, '_subtask') and self.task_manager._subtask:
                    current_detail = getattr(self.task_manager._subtask, 'sub_task_detail', '') or ''
                    new_detail = (current_detail + '\n' + content).strip() if current_detail else content
                    self.task_manager._subtask.sub_task_detail = new_detail
                    # self.task_manager.save()
                    return f"需求已追加到任务: {content}"
                return f"需求已记录(无活跃任务): {content}"
        else:
            return f"未知任务管理类型: {t}"
