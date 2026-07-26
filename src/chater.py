"""Chat 模式独立类

将 Chat 模式的 LLM 交互、工具调用、任务记忆管理从 Agent 中分离。
工作线程通过 chater.run() 执行对话，ToolExecutor 以 Chater 自身为 agent 上下文。
"""

import os, threading, queue

from llm_client import LLMClient
from logger import Logger
from task_manager import TaskManager
from stage_progress import StageProgress
from prompts import Prompts
from tools import TOOLS, ToolExecutor
from meta import TaskField, MsgType, MsgField, MsgStyle


class Chater:
    """Chat 模式独立类。

    职责：chat 模式的 LLM 对话、工具调用、记忆管理。
    ToolExecutor 以 Chater 自身为 agent，通过 self.agent.config
    访问 AppConfig。
    """

    def __init__(self, agent, config, logger, eqm):
        self._agent = agent
        self.config = config
        self.logger = logger
        self.eqm = eqm
        self.task_dir = config.paths.task_dir

        self.chat_llm = LLMClient(config.llm, eqm=eqm, logger=self.logger,
                                  log_history=config.log.history,user="chater")
        self.prompts = Prompts(config.paths.task_config_file_path)

        self.max_rounds = config.execution.max_rounds
        self.skills_dir = config.paths.skills_dir

        self.frontend_task_manager = None

        if self.eqm:
            self._start_chat_worker()

    # ── 日志 ──

    def _log(self, msg: str, always: bool = False):
        self.logger.log(msg)

    def add_conversation_entry(self, role: str, content: str):
        """委托给 frontend_task_manager 记录对话日志。"""
        if self.frontend_task_manager:
            self.frontend_task_manager.add_conversation_entry(role, content)

    # ── 初始化 ──

    def _chat_init(self, task_manager: TaskManager):
        """初始化 Chat 模式的任务管理及记忆。"""
        self.frontend_task_manager = task_manager
        project_path = self.frontend_task_manager.subtask.project_path
        self._init_task_memory(self.frontend_task_manager, self.chat_llm)
        self.tool_executor = ToolExecutor(project_path, agent=self,
                                          mode="chat", task_manager=self.frontend_task_manager)
        self.frontend_task_manager._stage_progress = StageProgress()

    def _init_task_memory(self, task_manager, llm):
        """初始化记忆：设置 memory_file，有快照则加载。"""
        sub = task_manager.subtask
        if not sub:
            return
        fpath = os.path.join(sub.project_path, ".memory", "memory.jsonl")
        # self.eqm.send_debug(f"加载记忆路径：{fpath}")
        llm.set_memory_file(fpath)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        if not os.path.exists(fpath):
            with open(fpath, "w") as _:
                pass
        task_manager.set_subtask_llm_context_info("memory.jsonl")
        task_manager.save()
        if os.path.exists(fpath):
            llm.load_memory()
            if llm.history:
                self._log(f"  📝 从快照恢复 LLM 上下文 ({len(llm.history)} 条消息)")

    # ── 工作线程 ──

    def _start_chat_worker(self):
        """启动 Chat 工作线程：从 to_chat_queue 取消息 → chater.run()"""

        def _chat_worker():
            Logger.mark_thread("chater")
            while True:
                msg = self.eqm.to_chat_queue.get()
                if msg.get(MsgField.TYPE) == MsgType.USER_INPUT:
                    content = msg.get(MsgField.CONTENT, "")
                    try:
                        self.frontend_task_manager.add_conversation_entry("user", content)
                        self.frontend_task_manager.save()
                        self.run(content)
                    except Exception as ex:
                        self.eqm.send_display(f"Error: {ex}", mode="chat",
                                              style=MsgStyle.ERROR)

        t = threading.Thread(target=_chat_worker, daemon=True)
        t.start()

    # ── 主入口 ──

    def run(self, user_message: str) -> dict:
        """对话模式主循环：LLM 多轮对话 + 工具调用。

        Returns: {"judge": str, "content": str}
        """

        pretask = self._agent.build_attach()
        prompt = (self.prompts.chat_prompt + pretask
                  + f"当前工作目录: {self.frontend_task_manager.subtask.project_path}\n所有文件操作请在此目录下进行。\n")
        # self.eqm.send_debug(f"chater prompt 中工作目录{self.frontend_task_manager.subtask.project_path}")
        msg = user_message
        rounds = 0
        while True:
            rounds += 1
            if rounds > self.max_rounds:
                self.eqm.send_display("超过最大调用次数", mode="chat",
                                      style=MsgStyle.WARN)
                return {TaskField.JUDGE: "false", "content": "超过最大调用次数"}

            # 排空队列，处理用户输入和控制消息
            drained = ""
            control_action = None
            if self.eqm:
                try:
                    while True:
                        m = self.eqm.to_chat_queue.get_nowait()
                        if m.get(MsgField.TYPE) == MsgType.USER_INPUT:
                            drained += m.get(MsgField.CONTENT, "") + "\n"
                            self.frontend_task_manager.add_conversation_entry("user", m.get(MsgField.CONTENT, ""))
                            self.frontend_task_manager.save()
                        elif m.get(MsgField.TYPE) == MsgType.CONTROL:
                            control_action = m.get(MsgField.CONTENT, "")
                            # 遇到 stop 立即停止排空，剩余消息留给后续阻塞等待处理
                            if control_action == "stop":
                                break
                except queue.Empty:
                    pass
                if control_action == "end":
                    self.eqm.send_display("⏹ 已结束", mode="chat")
                    return {TaskField.JUDGE: "false", "content": "用户结束执行"}
                if control_action == "stop":
                    self.eqm.send_display("⏸ 已暂停", mode="chat")
                    while True:
                        m = self.eqm.to_chat_queue.get()  # 阻塞等待
                        if m.get(MsgField.TYPE) == MsgType.CONTROL:
                            a = m.get(MsgField.CONTENT, "")
                            if a == "end":
                                self.eqm.send_display("⏹ 已结束", mode="chat")
                                return {TaskField.JUDGE: "false", "content": "用户结束执行"}
                            elif a == "stop":
                                continue
                        elif m.get(MsgField.TYPE) == MsgType.USER_INPUT:
                            drained += m.get(MsgField.CONTENT, "") + "\n"
                            self.frontend_task_manager.add_conversation_entry("user", m.get(MsgField.CONTENT, ""))
                            self.frontend_task_manager.save()
                            break
                if drained.strip():
                    msg = f"【用户新消息】\n{drained.strip()}\n\n【当前上下文】\n{msg}"
                    self._log(f"{msg}")

            result = self.chat_llm.chat_with_tools(prompt, msg, TOOLS,
                                                   use_memory=True)
            reasoning = result.get("reasoning_content", "")
            thinking_enabled = self.config.execution.thinking
            if reasoning and thinking_enabled:
                if self.eqm:
                    sentences = reasoning.split("。")
                    for s in sentences:
                        s = s.strip()
                        if s:
                            self.eqm.send_display(s, mode="chat",
                                                  style=MsgStyle.THINKING)

            if result["type"] == "tool_calls":
                total_len = 0
                for call in result["calls"]:
                    exec_result = self.tool_executor.execute(call["name"], call["args"])
                    exec_str = str(exec_result)
                    self.chat_llm.submit_tool_result(call["id"], exec_str)
                    total_len += len(exec_str)
                    if isinstance(exec_result, dict) and exec_result.get("type") == "finish":
                        summary = exec_result["summary"]
                        if summary:
                            return {"judge": "true", "content": summary}

                msg = f"本轮完成 {len(result['calls'])} 个工具调用"
                continue
            else:
                content_text = result.get("content", "")
                if content_text and self.eqm:
                    self.eqm.send_display(content_text, mode="chat")
                return {"judge": "true", "content": content_text}
