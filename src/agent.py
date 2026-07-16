"""核心 Agent

四阶段任务流水线，驱动 LLM 从任务分类到文档生成再到代码执行。

流程（run 方法）：
  阶段0: 任务分类
    └─ TaskClassifier.classify() / prompts.combined_classify → 分解归类
  阶段1: 文档生成（按类型路由）
    ├─ 开发类: _run_loop(comb_task) → LLM 自动生成需求文档
    ├─ 文本类: _run_loop(impl_task) → 生成文案/报告
    ├─ 调试类: _run_loop(impl_task) → 查阅 spc/ 后调试修复
    └─ 其他类: _run_loop(impl_task) → 直接执行
  阶段2: _run_loop(impl_task) [开发类]
    └─ LLM 读取 docs/ 需求文档实现代码
  阶段3: _run_loop(test_task) [开发类]
    └─ 基础验证、单元测试、使用说明书

每个阶段均有结果判断（judge）、日志记录、状态持久化。

路径策略：
  - 文件操作限定在 work_dir 内
  - spc/ 只读，docs/ 写入
  - work_dir 由 _resolve_subtask_dir 动态分配
"""

import os, re, time, sys, glob, json, threading, hashlib, queue
from datetime import datetime

from llm_client import LLMClient
from logger import Logger
from task_manager import TaskManager, SubTaskStatus, MainTaskStatus
from stage_progress import StageProgress
from prompts import Prompts
from tools import TOOLS, ToolExecutor, get_tools_excluding
from markdown_it import MarkdownIt
from event_queue_manager import EventQueueManager
from scheduler import TaskScheduler
from config import  MAX_HISTORY_CONTENT

from meta import TaskField, MsgType, MsgField, MsgStyle
from utils import Utils
from task_classifier import TaskClassifier



class Agent:
    """Agent 核心调度器

    职责：任务分类与拆解（阶段0）、按类型路由到对应执行流程、
    调用 _run_loop 进行多轮 LLM 交互执行、管理子任务生命周期。

    依赖组件：LLMClient / TaskManager / Logger
    """

    def __init__(self, config, auth_handler=None, eqm=None):
        self.config = config
        self.eqm = eqm
        self.auth = auth_handler

        self.max_rounds = config.execution.max_rounds

        self.logger = Logger(config.log, log_dir=config.paths.log_dir)

        memory_file = os.path.join(config.paths.memory_dir, "chat_context.md") if config.execution.memory_enabled else None
        self.chat_llm = LLMClient(config.llm, logger=self.logger, log_history=self.config.log.history, memory_file=memory_file)
        self.task_llm = LLMClient(config.llm, logger=self.logger, log_history=self.config.log.history)

        self.project_root = os.path.dirname(os.path.abspath(__file__))

        # 路径由 AppConfig.__post_init__ 解析为绝对路径并创建目录
        self.spc_dir = config.paths.spc_dir
        self.skills_dir = config.paths.skills_dir
        self.task_dir = config.paths.task_dir

        self.proj_path = os.path.join(self.config.execution.work_dir, "temp")
        self.docs_dir = None

        self.task_manager = TaskManager()
        self.enable_history_task_association = config.execution.enable_history_task_association

        self.prompts = Prompts(self.spc_dir, self.config.paths.task_config_file_path)

        self.scheduler = TaskScheduler(
            self.config.paths.pending_tasks_file_path,
            self
        )
        self.scheduler.start()
        self.is_interactive = False  # 当前任务是否为交互模式



        if self.eqm:
            self.start_chat_worker()
            self.start_task_worker()
    def _log(self, msg: str, always: bool = False):
        self.logger.log(msg)
    def start_task_worker(self):
        """启动后台工作线程：轮询调度器的到期任务队列并执行"""
        def _task_worker():
            Logger.mark_thread("task")
            while not self.scheduler._stopped.is_set():
                ready = self.scheduler.pop_ready_tasks()
                for rt in ready:
                    task_name = rt.get("task_name", "")
                    self.is_interactive = rt.get("is_interactive", False)
                    if task_name:
                        mode = rt.get("mode", "task")
                        self._log("=" * 30)
                        self.run(task_name, mode=mode)
                time.sleep(1)
        t = threading.Thread(target=_task_worker, daemon=True)
        t.start()

    def start_chat_worker(self):
        """启动 Chat 工作线程"""
        if not self.eqm:
            return
        def _chat_worker():
            Logger.mark_thread("chat")
            while True:
                msg = self.eqm.to_chat_queue.get()
                if msg.get(MsgField.TYPE) == MsgType.USER_INPUT:
                    content = msg.get(MsgField.CONTENT, "")
                    try:
                        self.run(content, mode="chat")
                    except Exception as ex:
                        self.eqm.send_display(f"Error: {ex}", mode="chat", style=MsgStyle.ERROR)
        t = threading.Thread(target=_chat_worker, daemon=True)
        t.start()

    def run(self, user_task: str, mode: str = "chat") -> dict:
        """主入口
        mode="chat": 对话模式（默认），无任务分解，直接进入工具调用对话
        mode="task": 任务模式，执行完整流水线（分类→分解→执行）

        Returns: {"judge": str, "content": str}
        """
        if self.eqm:
            self.eqm.reset_cancel(mode)

        if mode == "chat":
            ret= self._run_chat(user_task)

            self._log(f"\n{ret['content']}\n")
            return ret
        else:
            Utils.play_notification()
            # 任务模式：切换到独立 LLM 实例，避免污染对话上下文
            ret= self._run_task(user_task)
            ret_str = str(ret)

            if len(ret_str) > MAX_HISTORY_CONTENT:
                ret_str = ret_str[:MAX_HISTORY_CONTENT] + f"\n[... 省略 {len(ret_str) - MAX_HISTORY_CONTENT} 字符 ...]"
            if self.eqm:
                self.eqm.send_user_input("根据任务模式返回内容总结(无论成功禁止继续执行这个子任务):"+ret_str, mode="chat")
            return ret

    def _run_task(self, user_task: str) -> dict:
        """任务模式：以子任务为执行主体。

        1. 分类拆解 → 得到 orchestrate 列表
        2. 逐个执行子任务：
           - 延续子任务：加载历史 TaskManager，追加当前子任务
           - 全新子任务：以子任务名创建新 TaskManager
           - 每个子任务独立日志、计数器、花费
        """
        # ── 前置准备 ──
        os.makedirs(self.config.execution.work_dir, exist_ok=True)
        os.makedirs(self.skills_dir, exist_ok=True)
        self._generate_skills_index()
        self._generate_spc_index()
        self._generate_workspace_index()

        # ── 阶段 0: 任务分类与分解 ──
        self._log(f"\n{'='*60}")
        self._log(f"任务: {user_task}")
        self._log(f"模型: {self.task_llm.provider_name} / {self.task_llm.model}")
        self._log(f"{'='*60}\n")

        enable_history = self.enable_history_task_association
        self._log("阶段 0: " + ("任务分类与分解（含历史关联判断）" if enable_history else "任务分解"))

        self.task_llm.prepend_system_info()
        tc = TaskClassifier(self.task_llm, self.prompts)
        classification = tc.classify_with_history(user_task, self.task_dir, enable_history=enable_history)
        self.task_llm.history.clear()
        if TaskField.IS_FALSE(classification):
            self._log("\n❌ 任务分类失败")
            return TaskField.RET_JSON_FALSE(f"任务:{user_task} 分类失败")

        main_task = classification.get("main_task", user_task)
        orchestrate = classification.get("orchestrate", [])

        has_continuation = any(sub.get("related_task_file_name", "") for sub in orchestrate)
        self._log(f"  总任务: {main_task}")
        self._log(f"  拆解为 {len(orchestrate)} 个子任务（{'含延续' if has_continuation else '全新任务'}）：")
        
        total_results = []
        # ── 逐个执行子任务 ──
        for i, sub in enumerate(orchestrate, 1):
            sub_task = str(sub.get("sub_task", ""))
            task_type = str(sub.get("type", ""))
            sub_type = sub.get("sub_type", "")
            dir_from = sub.get("dir_from", "temp")

            # 从子任务自身字段判断是否延续
            has_related = bool(sub.get("related_task_file_name", ""))
            related_reason = sub.get("reason", "")
            related_task_file_name = sub.get("related_task_file_name", "")
            related_sub_idx = sub.get("related_sub_idx", 0)
            related_subtask_relation = sub.get("related_subtask_relation", "change")

            self._log(f"\n  [{i}/{len(orchestrate)}] {task_type} | {sub_task}")
            if self.eqm:
                self.eqm.send_display(sub_task, mode="task", msg_type=MsgType.TASK_NAME)

            # ── 每个子任务独立的日志和计数器 ──
            self.task_llm.history.clear()
            self.task_llm.init_task_counters()

            # ── 初始化/加载主任务（子任务为主体） ──
            # 每个子任务独立决定归属哪个主任务：
            #   - related_task_file_name 非空 → 加载历史主任务，把当前子任务挂上去
            #   - related_task_file_name 为空 → 以当前子任务名创建新的主任务
            related_sub_task = None
            if has_related:
                # 【延续子任务】通过文件名直接加载历史主任务
                state_file = os.path.join(self.task_dir, related_task_file_name) if related_task_file_name else ""
                self.task_manager = TaskManager.load(state_file) if (related_task_file_name and os.path.exists(state_file)) else self.task_manager

                if self.task_manager is not None:
                    self.task_manager.reactivate()
                    related_sub_task = self.task_manager.get_subtask(related_sub_idx)

                    if related_subtask_relation == "itself" and related_sub_task is not None:
                        # 【本身延续】直接复用历史子任务，不追加新子任务
                        self._log(f"  恢复历史任务 [{related_task_file_name}/{related_sub_idx}]: {related_sub_task.task[:50]}")
                        subtask_index = related_sub_idx
                    else:
                        # 【变更延续】追加新子任务到历史主任务下
                        new_idx = self.task_manager.append_subtasks([sub])
                        self.task_manager.set_subtask_extra(
                            new_idx, f"延续自 [{related_task_file_name}/{related_sub_idx}], 理由: {related_reason}"
                        )
                        self._log(f"  延续自历史任务 [{related_task_file_name}/{related_sub_idx}]: {related_sub_task.task[:50] if related_sub_task else '?'}")
                        subtask_index = new_idx
                else:
                    # 历史文件不可用，跳过该子任务并报告错误
                    self._log(f"  ❌ 历史文件未找到: {state_file}")
                    total_results.append({
                        TaskField.JUDGE: "false",
                        TaskField.SUB_TASK: sub_task,
                        TaskField.TASK_TYPE: task_type,
                        TaskField.SUB_TYPE: sub_type,
                        TaskField.SUBTASK_INDEX: 0,
                        TaskField.PROJECT_PATH: "",
                        TaskField.CONTENT: f"历史任务文件缺失: {state_file}",
                        TaskField.COST: "",
                    })
                    continue
            else:
                # 【全新子任务】创建以子任务名命名的主任务，只含一个子任务
                self.task_manager.start(sub_task)
                self.task_manager.add_subtasks_from_orchestrate([sub])
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.task_manager._save_path = os.path.join(self.task_dir, f"task_{ts}_state.json")
                subtask_index = 1


            self.task_manager.set_subtask_status(subtask_index, SubTaskStatus.IN_PROGRESS)

            # ── 解析项目目录（itself 跳过，直接用历史子任务的路径） ──
            if related_subtask_relation == "itself" and related_sub_task is not None:
                self.proj_path = related_sub_task.project_path or self.config.execution.work_dir
                self.docs_dir = os.path.join(self.proj_path, "docs")
            else:
                self._resolve_subtask_dir(
                    subtask_index, dir_from, subtask_content=sub_task,
                    is_continuation=has_related,
                    related_project_path=related_sub_task.project_path if (has_related and related_sub_task) else ""
                )

            # ── 执行阶段（itself 跳过历史关系设置） ──
            if related_subtask_relation != "itself":
                self.task_manager.set_subtask_history_relation(subtask_index, has_related, related_sub_task.task if related_sub_task else "", related_sub_task.project_path if related_sub_task else "")
            
            
            result = self._run_phases(subtask_index)

            self.task_manager.set_subtask_result(subtask_index, result["judge"], result["content"],
                                                 rounds=self.task_llm.call_count)
            self._log(f"  💾 保存状态到: {self.task_manager._save_path}")
            self.task_manager.save_plan_steps(self.task_manager._stage_progress)

            cost_str=  self.task_llm.get_cost_summary() + self.task_llm.get_cost_from_balance()

            total_results.append({
                TaskField.JUDGE: result["judge"],
                TaskField.SUB_TASK: sub_task,
                TaskField.TASK_TYPE: task_type,
                TaskField.SUB_TYPE: sub_type,
                TaskField.SUBTASK_INDEX: subtask_index,
                TaskField.PROJECT_PATH: self.proj_path,
                TaskField.TASK_STATE: self.task_manager._save_path,
                TaskField.COST: cost_str,
                TaskField.CONTENT: result["content"],
            })

            # ── 子任务完成报告 ──
            if result["judge"] == "true":
                self.task_manager.set_subtask_status(subtask_index, SubTaskStatus.COMPLETED)
                self.task_manager.finish(True)
                self._log(f"\n子任务{subtask_index}完成 — " +cost_str)
            else:
                self.task_manager.set_subtask_status(subtask_index, SubTaskStatus.FAILED)
                self.task_manager.save_plan_steps(self.task_manager._stage_progress)

        # ── 全部子任务完成，汇总各子任务结果 ──
        summary_lines = [f"✅ 全部 {len(total_results)} 个子任务完成"]
        for r in total_results:
            judge = r.get(TaskField.JUDGE, "false")
            sub = r.get(TaskField.SUB_TASK, "")
            icon = "✅" if judge == "true" else "❌"
            project = r.get(TaskField.PROJECT_PATH, "")
            summary_lines.append(f"{icon} [{r.get(TaskField.TASK_TYPE, "")}] {sub}")
            if project:
                summary_lines.append(f"     项目: {project}")
            if r.get(TaskField.CONTENT):
                cnt = r[TaskField.CONTENT]
                summary_lines.append(f"     结果: {cnt[:200]}{'...' if len(cnt) > 200 else ''}")
            if r.get(TaskField.COST):
                summary_lines.append(f"     {r[TaskField.COST]}")
        summary = "\n".join(summary_lines)
        self._log(f"\n{summary}")
        self.task_manager.save_plan_steps(self.task_manager._stage_progress)
        return TaskField.RET_JSON_TRUE(summary)

    def _run_phases(self, subtask_index: int) -> bool:
        """按任务属性定义循环执行各阶段 run_loop

        Returns: 
        """
        sub = self.task_manager.get_subtask(subtask_index)
        if sub is None:
            self._log(f"  ⚠️ 子任务{subtask_index}未找到，跳过")
            return False
        
        # 恢复之前中断的子任务
        if sub.llm_context_info:
            result = self._run_loop(subtask_index, base_prompt="")
            self.task_manager.save_plan_steps(self.task_manager._stage_progress)
            return result
        
        result = self._get_subtask_phases_and_prompt(sub.task_type, sub.sub_type)
        if result is None:
            self._log(f"  ⚠️ spec.md 中未找到 {sub.task_type} (sub_type={sub.sub_type}) 的阶段定义，跳过")
            return False
        phases = result['phases']
        
        extra_prompt = result.get('extra_prompt', '')
        if isinstance(extra_prompt, list):
            extra_prompt = "\n".join(extra_prompt)

        # 构建任务级别 extra_prompt：pretask + 任务元信息 + 历史延续信息（所有 phase 共享）
        pretask = self._build_pretask_skills()
        extra_prompt_add = "\n" + pretask
        extra_prompt_add += "\n"+"# 当前项目：\n"
        extra_prompt_add += f"当前任务: {sub.task}\n"
        extra_prompt_add += f"任务类别: {sub.task_type}\n"
        if sub.sub_type:
            extra_prompt_add += f"子类型: {sub.sub_type}\n"
        if sub.is_continuation:
            extra_prompt_add += (
                f"关联子任务: {sub.related_subtask_task}\n"
                f"关联项目路径: {sub.related_project_path}\n"
            )
        extra_prompt_add+=f"当前项目目录: {self.proj_path}\n所有文件操作请在此目录下进行。\n"
        extra_prompt= extra_prompt_add+extra_prompt+"\n"
        extra_prompt+= "- 任务需要分阶段分步骤规划完成，不可忽略已经存在的阶段，但可根据需求新增阶段"\
                        "- 如果阶段缺少详细步骤，先调用 update_plan 规划。\n"\
                        "- 每个步骤完成后及时更新状态。\n"\
                        "- 所有步骤完成后调用 finish 结束本任务。"


        # 构建完整 system prompt（含 tools JSON、项目目录、阶段数、extra_prompt）
        task_tools = get_tools_excluding("start_task")
        system_prompt = (
            self.prompts.task_prompt_exclude_tools
            + "\n"
            + json.dumps(task_tools, ensure_ascii=False)
        )
        if extra_prompt:
            system_prompt += "\n" + extra_prompt

       
            
        print(f"[DEBUG] system_prompt 长度: {len(system_prompt)}, extra_prompt 部分:\n {extra_prompt}\n")

        # 预构建各 phase 消息（仅包含当前阶段名 + [M] 内容 + [P] 内容）
        phase_msgs = []
        for phase_idx, phase in enumerate(phases):
            phase_name = phase['name']
            phase_msg_items = phase.get('phase_msg', [])

            lines_p = []
            for item in phase_msg_items:
                lines_p.append(item)
            full_msg = '\n'.join(lines_p)

            phase_msgs.append({
                "name": phase_name,
                "msg": full_msg,
            })
            print(f"[DEBUG _run_landscape] phase '{phase_name}': msg={full_msg[:100]}")
            self._log(f"  阶段 {phase_idx+1}/{len(phases)}: {phase_name}")

        self.task_manager.set_subtask_phase_msgs(subtask_index, phase_msgs)

        result = self._run_loop(subtask_index, base_prompt=system_prompt)

        self.task_manager.save_plan_steps(self.task_manager._stage_progress)
        return result

    def _get_subtask_phases_and_prompt(self, task_type_key: str, sub_type: str = ""):
        """从 TaskAttributeManager 获取指定 task type 的阶段列表

        Returns:
            {"phases": [{"name": ..., "phase_msg": [...]}], "extra_prompt": "..."}
            或 None（未找到匹配项或 sub_type 不匹配）
        """
        if not hasattr(self, '_attr_mgr'):
            from task_attribute_manager import TaskAttributeManager
            json_path = self.config.paths.task_config_file_path
            self._attr_mgr = TaskAttributeManager(json_path)
        result = self._attr_mgr.get_subtask_phases_and_prompt(task_type_key, sub_type)
        if result is None:
            self._log(
                f"  ⚠️ 任务子类型 '{sub_type}' 不在大类 '{task_type_key}' 的可用子类型中",
                
            )
        return result

    def _scan_skills_dir(self) -> str:
        """扫描 skills_dir 构建技能列表文本"""
        if not self.skills_dir or not os.path.isdir(self.skills_dir):
            return ""

        lines = ["## 可用技能（优先查看是否有可用技能）："]
        for skill_dir in sorted(glob.glob(os.path.join(self.skills_dir, "*"))):
            if not os.path.isdir(skill_dir):
                continue
            name = os.path.basename(skill_dir)
            md = os.path.join(skill_dir, "SKILL.md")
            desc = ""
            if os.path.isfile(md):
                try:
                    with open(md, "r", encoding="utf-8") as f:
                        first = f.readline().strip().lstrip("#").strip()
                        if first:
                            desc = first
                except Exception:
                    pass
            lines.append(f"- **{name}**: {desc or name}")
            lines.append(f"  文档: {md}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def _scan_docs_dir(self) -> str:
        """扫描 docs_dir 构建项目文档列表文本"""
        if not self.docs_dir or not os.path.isdir(self.docs_dir):
            return ""

        docs = sorted(glob.glob(os.path.join(self.docs_dir, "*.md")))
        if not docs:
            return ""

        lines = ["\n## 当前子任务参考文档"]
        for mdp in docs:
            name = os.path.splitext(os.path.basename(mdp))[0]
            desc = ""
            try:
                with open(mdp, "r", encoding="utf-8") as f:
                    first = f.readline().strip().lstrip("#").strip()
                    if first:
                        desc = first
            except Exception:
                pass
            lines.append(f"- **{name}**: {desc or name}")
            lines.append(f"  文件: {mdp}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def _build_pretask_skills(self) -> str:
        """构建可用技能列表文本"""
        return self._scan_skills_dir()

    def _build_pretask_prjdocs(self) -> str:
        """构建项目文档列表文本"""
        return self._scan_docs_dir()

    def _run_chat(self, user_message: str) -> dict:
        """对话模式：简单的一轮或多轮 LLM 对话，支持工具调用和 start_task"""

        self.is_interactive = True  # chat 模式默认为交互模式
        executor = ToolExecutor(self.config.execution.work_dir, logger=self.logger, agent=self, eqm=self.eqm, mode="chat")

        pretask = self._build_pretask_skills() + self._build_pretask_prjdocs()

        prompt =  self.prompts.chat_prompt+ pretask 

        msg=  user_message
        # 初始化 StageProgress（chat 模式无预定义阶段，LLM 通过 update_plan 动态创建）
        self.chat_stage_progress = StageProgress()
        rounds = 0
        while True:
            if self.eqm and self.eqm.is_cancelled("chat"):
                self.eqm.send_display("⏹ 已取消", mode="chat")
                return {TaskField.JUDGE: "false", "content": "用户取消了执行"}
            rounds += 1
            if rounds > self.max_rounds:
                return {TaskField.JUDGE: "false", "content": "超过最大调用次数"}

            # 检查是否有新消息进来（工具执行期间用户可能发了新消息）
            drained = ""
            if self.eqm:
                try:
                    while True:
                        m = self.eqm.to_chat_queue.get_nowait()
                        if m.get(MsgField.TYPE) == MsgType.USER_INPUT:
                            drained += m.get(MsgField.CONTENT, "") + "\n"
                except queue.Empty:
                    pass
                if drained.strip():
                    msg = f"【用户新消息】\n{drained.strip()}\n\n【当前上下文】\n{msg}"
           
            result = self.chat_llm.chat_with_tools(prompt, msg, TOOLS, use_memory=True)
            reasoning = result.get("reasoning_content", "")
            if reasoning:
                if self.eqm:
                    sentences = reasoning.split("。")
                    for s in sentences:
                        s = s.strip()
                        if s:
                            self.eqm.send_display(s, mode="chat", style=MsgStyle.THINKING)
            if result["type"] == "tool_calls":
                total_len = 0
                for call in result["calls"]:
                    exec_result = executor.execute(call["name"], call["args"])
                    exec_str = str(exec_result)
                    self.chat_llm.submit_tool_result(call["id"], exec_str)
                    total_len += len(exec_str)
                    if isinstance(exec_result, dict) and exec_result.get("type") == "finish":
                        summary = exec_result["summary"]
                        if summary:
                            return {"judge": "true", "content": summary}
                msg = f"[工具执行完毕，{len(result['calls'])} 个结果，总计 {total_len} 字符]"
                continue
            else:
                content_text = result.get("content", "")
                if content_text and self.eqm:
                    self.eqm.send_display(content_text, mode="chat")

                return {"judge": "true", "content": content_text}

    def _load_llm_context(self, sub) -> tuple[str, list]:
        """从 context_prompt.json 恢复 base_prompt 和 LLM 上下文"""
        if not sub or not sub.llm_context_info:
            return "", []
        fpath = os.path.join(sub.project_path or self.config.execution.work_dir, ".llm_context", "context_prompt.json")
        if not os.path.exists(fpath):
            return "", []
        try:
            with open(fpath, encoding="utf-8") as f:
                snap = json.load(f)
            bp = snap.get("base_prompt", "")
            ctx = snap.get("context", [])
            if bp:
                self._log(f"  📝 从快照恢复 base_prompt ({len(bp)} chars)")
            if ctx:
                self._log(f"  📝 从快照恢复 LLM 上下文 ({len(ctx)} 条消息)")
            return bp, ctx
        except Exception:
            return "", []

    def _save_llm_context(self, subtask_index: int, base_prompt: str = ""):
        """保存当前 LLM 上下文到 context_prompt.json"""
        ctx_data = {
            "base_prompt": base_prompt,
            "context": self.task_llm.history,
        }
        ctx_json = json.dumps(ctx_data, ensure_ascii=False, indent=2)

        sub = self.task_manager.get_subtask(subtask_index)
        proj = sub.project_path if sub and sub.project_path else self.config.execution.work_dir
        save_dir = os.path.join(proj, ".llm_context")
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, "context_prompt.json")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(ctx_json)

        self.task_manager.set_subtask_llm_context_info(subtask_index, "context_prompt.json")
        self._log(f"  📝 LLM 上下文已保存: {filepath}")

    def _run_loop(self, subtask_index: int, base_prompt: str = "") -> dict:
        """工具调用模式执行循环。
        当前子任务的某个阶段在此处执行
        用 chat_with_tools 替代 IMP_FORMAT JSON 流程。
        LLM 通过 finish 工具标记完成/失败。
        当 phases 传入时，finish 成功后自动切换到下一阶段提示词，
        在同一对话中继续执行。

        Returns: {"judge": str, "content": str}
        """

        sub = self.task_manager.get_subtask(subtask_index)
        
        if not base_prompt:
            base_prompt, ctx_msgs = self._load_llm_context(sub)
            if ctx_msgs:
                self.task_llm.history = ctx_msgs
       

        executor = ToolExecutor(sub.project_path, logger=self.logger, agent=self, eqm=self.eqm, mode="task")

        self._log(f"工作目录proj: {sub.project_path}")

        task_tools = get_tools_excluding("start_task")
        
        if sub and sub.phase_msgs:
            self.task_manager._stage_progress = self.task_manager.load_stage_progress(
                [p["name"] for p in sub.phase_msgs])
            status = self.task_manager._stage_progress.format_status()
            msg = f"# 当前任务: {sub.task}\n\n{status}\n\n"
                   

            self._log(f"[PHASE] prompt={len(base_prompt)}chars | msg= {msg}")


        for num in range(self.max_rounds):
            if self.eqm and self.eqm.is_cancelled("task"):
                self.eqm.send_display("⏹ 已取消", mode="task")
                return {TaskField.JUDGE: "false", "content": "用户取消了执行"}
            result = self.task_llm.chat_with_tools(base_prompt, msg, task_tools)
            # 打印思考信息
            reasoning = result.get("reasoning_content", "")
            if reasoning:
                print(f"[debug] model={self.config.llm.model}, reasoning={len(reasoning)} chars")
                if self.eqm:
                    sentences = reasoning.split("。")
                    for s in sentences:
                        s = s.strip()
                        if s:
                            self.eqm.send_display(s, mode="task", style=MsgStyle.THINKING)
            # 获取非工具返回内容
            content_text = result.get("content", "")
            if content_text:
                self._log(f"\n📩{content_text}")

            if result["type"] == "tool_calls":
                for call in result["calls"]:
                    self._log(f"共: {self.max_rounds}, 第 {num} 轮  🔧 {call['name']}({call['args']})")
                    exec_result = executor.execute(call["name"], call["args"])

                    if isinstance(exec_result, dict) and exec_result.get("type") == "finish":
                        # 提交 tool 响应，满足协议要求
                        self.task_llm.submit_tool_result(call["id"], str(exec_result))

                        if not exec_result["success"]:
                            self.task_manager.set_subtask_result(
                                subtask_index, "false", exec_result["summary"])
                            self.task_manager.set_subtask_status(
                                subtask_index, SubTaskStatus.FAILED)
                            self._save_llm_context(subtask_index, base_prompt)
                            self._log(f"\n  {self.task_manager._stage_progress.format_status()}")
                            self.task_manager.update_task_list(self.task_dir) 
                            return TaskField.RET_JSON_FALSE(exec_result["summary"])
                        
                        all_done = all(
                            sub.plan_steps.get(p['name']) and
                            all(s.get('status', '') == 'completed' for s in sub.plan_steps.get(p['name'], []))
                            for p in sub.phase_msgs
                        ) if sub.plan_steps else False

                        if all_done:
                            self.task_manager.set_subtask_status(
                                subtask_index, SubTaskStatus.COMPLETED)
                            
                            self._save_llm_context(subtask_index, base_prompt)
                            self._log(f"\n任务总结: {exec_result['summary']}")
                            self.task_manager.update_task_list(self.task_dir)
                            
                            return TaskField.RET_JSON_TRUE(exec_result["summary"])
                    else:
                        self.task_llm.submit_tool_result(call["id"], str(exec_result))

                    self._log(f"     → {str(exec_result)[:500]}")

                # 收敛压力：根据已消耗轮次注入提示
                rounds_used = num + 1
                convergence = ''
                if rounds_used >= self.max_rounds * 0.5:
                    convergence = (
                        f'\n[⚠ 已消耗 {rounds_used}/{self.max_rounds} 轮，'
                        f'如当前任务无法在剩余轮次内完成，请调用 finish(success=False) 结束。]'
                    )
                elif rounds_used >= self.max_rounds * 0.25:
                    convergence = (
                        f'\n[{rounds_used}/{self.max_rounds} 轮，请精简操作、避免反复读写。]'
                    )

                if convergence:
                    base = f"所有阶段进度:\n{self.task_manager._stage_progress.format_status()}"
                    msg = base + "\n" + convergence

            elif result["type"] == "error":
                self._log(f"\n❌ API错误: {result.get('message', '')}\n")
                return TaskField.RET_JSON_FALSE(result.get("message", "API错误"))
            continue

        if num+1 >= self.max_rounds:
            self._save_llm_context(subtask_index, base_prompt)

        return TaskField.RET_JSON_FALSE(f"达到最大轮次 ({self.max_rounds})，任务未完成")

    def _generate_skills_index(self):
        """扫描 skills_dir，生成 skills_index.json"""

        index = []
        sd = self.skills_dir
        if os.path.isdir(sd):
            for name in sorted(os.listdir(sd)):
                d = os.path.join(sd, name)
                if os.path.isdir(d) and os.path.exists(os.path.join(d, "SKILL.md")):
                    meta_path = os.path.join(d, "skill.json")
                    meta = {}
                    if os.path.exists(meta_path):
                        try:
                            meta = json.load(open(meta_path))
                        except Exception:
                            pass
                    index.append({
                        "name": name,
                        "description": meta.get("description", ""),
                        "md_path": os.path.join(d, "SKILL.md"),
                        "schema": meta.get("schema", {}),
                        "entrypoint": meta.get("entrypoint", ""),
                        "invoke": meta.get("invoke", "cli"),
                    })
        idx_path = os.path.join(self.skills_dir, "skills_index.json")
        with open(idx_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        self.logger.write(f"skills_index.json: {len(index)} 个技能")

    @staticmethod
    def _scan_md_dir(dir_path: str, source_label: str) -> list:
        result = []
        if not os.path.isdir(dir_path):
            return result
        for md_path in sorted(glob.glob(os.path.join(dir_path, "*.md"))):
            desc = ""
            try:
                with open(md_path, 'r', encoding='utf-8') as f:
                    first = f.readline().strip().lstrip("#").strip()
                    if first:
                        desc = first
            except Exception:
                pass
            result.append({
                "name": os.path.splitext(os.path.basename(md_path))[0],
                "description": desc or os.path.basename(md_path),
                "path": md_path,
                "source": source_label,
            })
        return result

    def _generate_spc_index(self):
        """扫描 spc_dir，生成 spc_index.json"""

        index = self._scan_md_dir(self.spc_dir, "spc")
        idx_path = os.path.join(self.spc_dir, "spc_index.json")
        with open(idx_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        self.logger.write(f"spc_index.json: {len(index)} 个文档")

    def _generate_workspace_index(self):
        """扫描 work_dir 全部文件，生成 workspace_index.json"""

        index = []
        wd = self.config.execution.work_dir
        if not os.path.isdir(wd):
            return
        for root, dirs, files in os.walk(wd):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "log"]
            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, wd)
                index.append({
                    "name": fname,
                    "path": fpath,
                    "relpath": rel,
                    "size": os.path.getsize(fpath),
                })
        idx_path = os.path.join(wd, "workspace_index.json")
        with open(idx_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        self.logger.write(f"workspace_index.json: {len(index)} 个文件")

    def _resolve_subtask_dir(self, subtask_index: int, dir_from: str,
                             subtask_content: str = "",
                             is_continuation: bool = False,
                             related_project_path: str = "") -> str:
        """解析子任务工作目录

        优先级: reuse → [建议名]（交互询问）→ [建议名]（直接使用）→ temp
        """

        # ── reuse: 复用历史目录或上一个子任务的目录 ──
        if dir_from == "reuse":
            # reuse 仅用于历史延续，非延续时回退到 workspace
            if is_continuation and related_project_path:
                proj_path = related_project_path
            else:
                proj_path = os.path.join(self.config.execution.work_dir, "temp")
            proj_name = os.path.basename(proj_path.rstrip("/")) or "temp"

        # ── [建议名]: 交互模式询问用户，非交互直接用建议名 ──
        elif dir_from.startswith("[") and dir_from.endswith("]"):
            suggested = dir_from[1:-1].strip() or "temp"
            proj_name = suggested
            if self.is_interactive:
                prompt = f"子任务 [{subtask_index}] 请输入项目目录名 [{suggested}]"
                if self.eqm is not None:
                    try:
                        Utils.play_notification()
                        user_input = self.eqm.ask_user(prompt, mode="task").strip()
                        if user_input:
                            proj_name = user_input
                    except Exception:
                        pass
                elif __import__("threading").current_thread() is __import__("threading").main_thread():
                    try:
                        user_input = input(
                            f"\n📁 {prompt}: "
                        ).strip()
                        if user_input:
                            proj_name = user_input
                    except (EOFError, KeyboardInterrupt):
                        pass
            proj_path = os.path.join(self.config.execution.work_dir, proj_name)

        # ── temp 或其他: 使用 temp 目录 ──
        else:
            proj_name = "temp"
            proj_path = os.path.join(self.config.execution.work_dir, "temp")

        os.makedirs(proj_path, exist_ok=True)
        docs_dir = os.path.join(proj_path, "docs")
        os.makedirs(docs_dir, exist_ok=True)

        self.task_manager.set_subtask_project(subtask_index, proj_path, docs_dir)
        self.proj_path = proj_path
        self.config.execution.work_dir = proj_path
        self.docs_dir = docs_dir

        self._log(f"   目录策略: {dir_from} → {proj_path}")
        return proj_path

 
