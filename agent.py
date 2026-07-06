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

import os, re, time, sys, glob, json, threading
from datetime import datetime

from llm_client import LLMClient
from config import TRUNCATION
from logger import Logger
from task_manager import TaskManager, SubTaskStatus, MainTaskStatus
from stage_progress import StageProgress
from prompts import Prompts
from tools import TOOLS, ToolExecutor, get_tools_excluding
from markdown_it import MarkdownIt
from scheduler import TaskScheduler

from task_classifier import TaskClassifier


class Agent:
    """Agent 核心调度器

    职责：任务分类与拆解（阶段0）、按类型路由到对应执行流程、
    调用 _run_loop 进行多轮 LLM 交互执行、管理子任务生命周期。

    依赖组件：LLMClient / TaskManager / Logger
    """

    def __init__(self, config: dict, auth_handler=None):
        self.config = config
        llm_cfg = config.get("llm", {})
        mem_cfg = config.get("memory", {})
        llm_cfg["memory_enabled"] = mem_cfg.get("enabled", True)
        llm_cfg["memory_size"]    = mem_cfg.get("size", 20)
  
        self.auth       = auth_handler

        exec_cfg = config.get("execution", {})
        self.max_rounds   = exec_cfg.get("llm_rounds", 10)
        log_cfg = config.get("log", {})
        
        self.logger    = Logger()
        self.logger.log_to_terminal = log_cfg.get("log_to_terminal", False)
        self.logger.enabled = log_cfg.get("log_to_file", True)

        self.chat_llm  = LLMClient(llm_cfg, logger=self.logger)

        self.task_llm  = LLMClient(llm_cfg, logger=self.logger)



        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.work_dir = os.getcwd()
        # spc_dir
        scd = exec_cfg.get("spc_dir", "./spc")
        if not os.path.isabs(scd):
            scd = os.path.join(self.project_root, scd)
        self.spc_dir = os.path.abspath(scd)
        
        self.proj_path = os.path.join(self.work_dir, "temp")
        self.docs_dir = None
        # skills_dir
        sd = exec_cfg.get("skills_dir", "./inner_space/skills")
        if not os.path.isabs(sd):
            sd = os.path.join(self.project_root, sd)
        self.skills_dir = os.path.abspath(sd)
        # log_dir
        ld = log_cfg.get("dir") or os.path.join(self.work_dir, "log")
        if not os.path.isabs(ld):
            ld = os.path.join(self.project_root, ld)
        self.log_dir = os.path.abspath(ld)
        # task_dir
        td = exec_cfg.get("task_dir", "./task")
        if not os.path.isabs(td):
            td = os.path.join(self.project_root, td)
        self.task_dir = os.path.abspath(td)

        self.task_manager = TaskManager()
        self.enable_history_association = exec_cfg.get("enable_history_association", True)

        self.prompts = Prompts(self.spc_dir)

        os.makedirs(self.task_dir, exist_ok=True)
        self._exec_lock = threading.Lock()
        self.scheduler = TaskScheduler(
            os.path.join(self.task_dir, "pending_tasks.json"),
            self
        )
        self.scheduler.start()
        self.is_interactive = False  # 当前任务是否为交互模式
        self._start_task_worker()

        # 初始化日志文件（所有模式都需要，不仅仅是 task 模式）
        os.makedirs(self.log_dir, exist_ok=True)
        if not self.logger.path:
            self.logger.init(self.log_dir)
        if log_cfg.get("history", True):
            self.chat_llm.history_log_path = os.path.join(self.log_dir, "history_chat.log")
            self.task_llm.history_log_path = os.path.join(self.log_dir, "history_task.log")


    def _log(self, msg: str, always: bool = False):
        self.logger.log(msg, always)

    def _start_task_worker(self):
        """启动后台工作线程：轮询调度器的到期任务队列并执行"""
        def _worker():
            while not self.scheduler._stopped.is_set():
                ready = self.scheduler.pop_ready_tasks()
                for rt in ready:
                    task_name = rt.get("task_name", "")
                    self.is_interactive = rt.get("is_interactive", False)
                    if task_name:
                        mode = rt.get("mode", "task")
                        self._log(f"\n{"="*30}⏰ 定时任务{task_name[:15]}.. 🚀{"="*30}", always=True)
                        ret = self.run(task_name, mode=mode)
                        self._log(f"\n{ret["content"]}", always=True)
                        self._log(f"\n{"="*40}✅ 任务执行结束{"="*40}", always=True)

                time.sleep(1)
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def run(self, user_task: str, mode: str = "chat") -> dict:
        """主入口

        线程安全：通过 self._exec_lock 确保定时器线程与主线程不会并发执行。

        mode="chat": 对话模式（默认），无任务分解，直接进入工具调用对话
        mode="task": 任务模式，执行完整流水线（分类→分解→执行）

        Returns: {"judge": str, "content": str}
        """
        # with self._exec_lock:
        if mode == "chat":
            # print(f"\n🤖: {self.chat_llm.dump_history()}")
            self._in_task_mode = False
            ret= self._run_chat(user_task)
            print(self.chat_llm.dump_history())

            self._log(f"\n🤖: {ret["content"]}\n",always=True)
            return ret
        else:
            # 任务模式：切换到独立 LLM 实例，避免污染对话上下文
            self._in_task_mode = True

            try:
                ret= self._run_task(user_task)
                return ret
            finally:
                self._in_task_mode = False

    def _run_task(self, user_task: str) -> dict:

        """任务模式：完整流水线"""
        self._log(f"\n{'='*60}")
        self._log(f"任务: {user_task}")
        self._log(f"模型: {self.task_llm.provider_name} / {self.task_llm.model}")
        self._log(f"{'='*60}\n")

        self.task_llm.history.clear()  # 清掉上一个task的历史记录

        self.task_llm.prepend_system_info()

        os.makedirs(self.work_dir, exist_ok=True)
        os.makedirs(self.skills_dir, exist_ok=True)
        self._generate_skills_index()
        self._generate_spc_index()
        self._generate_workspace_index()
        self._init_log()

        # ================================================================
        # 阶段 0: 任务分类与分解
        # ================================================================
        self._log("\n阶段 0：收到任务："+user_task+"\n")

        enable_history = self.enable_history_association
        if enable_history:
            self._log("阶段 0: 任务分类与分解（含历史关联判断）")
        else:
            self._log("阶段 0: 任务分解（配置已禁用历史任务关联）")

        classification = self._classify_with_history(user_task, enable_history=enable_history)
        self.task_llm.history.clear()  # 清掉分类阶段产生的历史，避免污染 _run_loop
        if classification is None:
            self._log("\n❌ 任务分类失败，任务终止", always=True)
            return {"judge": "false", "content": "阶段0：任务分类失败（LLM 返回解析错误）"}

        is_continuation = classification.get("is_continuation", False)

        if is_continuation:
            hist_idx = classification.get("history_task_index", 0)
            sub_idx = classification.get("subtask_index", 0)
            reason = classification.get("reason", "")
            orchestrate = classification.get("orchestrate", [])
            if not orchestrate:
                self._log("\n❌ 延续任务无子任务，终止", always=True)
                return {"judge": "false", "content": "历史任务延续无有效子任务"}

            history_tasks = TaskManager.scan_history_tasks(self.task_dir)
            history_main_task = ""
            hist_file = ""
            if 0 <= hist_idx - 1 < len(history_tasks):
                history_main_task = history_tasks[hist_idx - 1].get("main_task", "")
                hist_file = history_tasks[hist_idx - 1].get("file", "")

            if not hist_file or not os.path.exists(hist_file):
                self._log(f"\n❌ 历史任务文件未找到: {hist_file}", always=True)
                return {"judge": "false", "content": f"历史任务文件不存在: {hist_file}"}

            self.task_manager = TaskManager.load(hist_file)
            self.task_manager.reactivate()
            self._task_state_path = hist_file

            base_idx = self.task_manager.append_subtasks(orchestrate)
            for j, sub in enumerate(orchestrate):
                new_idx = base_idx + j
                self.task_manager.set_subtask_extra(
                    new_idx,
                    f"延续自历史任务 [{hist_idx}] 主任务: {history_main_task}, 子任务: [{sub_idx}], "
                    f"理由: {reason}"
                )

            self._log(f"\n📋 历史任务延续")
            self._log(f"  历史主任务 [{hist_idx}]: {history_main_task}")
            self._log(f"  关联子任务: [{sub_idx}]")
            self._log(f"  判断理由: {reason}")
            self._log(f"  新子任务 ({len(orchestrate)} 个，索引 {base_idx}-{base_idx+len(orchestrate)-1}):")
            for sub in orchestrate:
                self._log(f"    [{sub.get('type','')}] {sub.get('sub_task','')}")

            self.task_manager.add_conversation_entry("user", user_task)
            self.task_manager.add_conversation_entry(
                "assistant",
                f"识别为历史任务延续 → 追加 {len(orchestrate)} 个子任务 (主任务: {history_main_task})"
            )
            self.task_manager.add_conversation_entry(
                "agent", f"历史任务延续: {history_main_task} → 子任务{sub_idx}，追加 {len(orchestrate)} 个新子任务"
            )

            hist_sub = self.task_manager.get_subtask(sub_idx)
            hist_project_path = hist_sub.project_path if hist_sub and hist_sub.project_path else self.work_dir
            hist_docs_dir = hist_sub.docs_dir if hist_sub and hist_sub.docs_dir else ""

            _cont_subtask_content = hist_sub.content if hist_sub else ""
            _cont_project_path = hist_project_path
            subtask_start_idx = base_idx
            main_task = history_main_task

        else:
            main_task = classification.get("main_task", user_task)
            _cont_subtask_content = ""
            _cont_project_path = ""
            subtask_start_idx = 1
            orchestrate = classification.get("orchestrate", [])
            self._log(f"  总任务: {main_task}")
            self._log(f"  拆解为 {len(orchestrate)} 个子任务：")
            for sub in orchestrate:
                st = sub.get("sub_task", "")
                stype = sub.get("type", "")
                sstype = sub.get("sub_type", "")
                self._log(f"    [{stype}] {st} (sub_type={sstype})")

            self.task_manager.start(main_task)
            self.task_manager.add_subtasks_from_orchestrate(orchestrate)
            self.task_manager.add_conversation_entry("user", user_task)
            self.task_manager.add_conversation_entry(
                "assistant", f"将任务分解为 {len(orchestrate)} 个子任务: {main_task}"
            )
            self._save_task_state()

            # ================================================================
            # 阶段 1: 任务分析及规划
            # ================================================================
            self._log("\n阶段 1: 任务分析及规划")

        for i, sub in enumerate(orchestrate, subtask_start_idx):
            task_type = str(sub.get("type", ""))
            sub_task = str(sub.get("sub_task", ""))
            sub_type = sub.get("sub_type", "")
            dir_from = sub.get("dir_from", "temp")

            self._log(f"\n  [{i}/{len(orchestrate)}] {task_type} | {sub_task}")

            self.task_manager.add_conversation_entry(
                "agent", f"开始执行子任务 [{i}/{len(orchestrate)}]: [{task_type}] {sub_task}",
                subtask_index=i
            )
            self.task_manager.set_subtask_status(i, SubTaskStatus.IN_PROGRESS)

            self._resolve_subtask_dir(
                i, dir_from, subtask_content=sub_task,
                is_continuation=is_continuation,
                related_project_path=_cont_project_path if is_continuation else ""
                )
            
          
            # 子任务执行
            result = self._run_phases(task_type, sub_task, sub_type, i,
                             is_continuation, main_task,
                             _cont_subtask_content, _cont_project_path)
    
            self.task_manager.set_subtask_result(i, result["judge"], result["content"])
            self._save_task_state()
            if result["judge"]!="true":
                self.task_manager.finish(False)
                self.task_manager.add_conversation_entry("agent", f"子任务{i}失败")
                self._save_task_state()
                return {"judge": "false", "content": f"子任务{i}失败"}


        self.task_manager.finish(True)
        summary = self.task_manager.summary()
        self._log(f"\n{summary}")
        self.task_manager.add_conversation_entry("agent", f"\n{summary}")

        self._save_task_state()
        return {"judge": "true", "content": f"\n{summary}"}


    def _run_phases(self, sp_key: str, sub_task: str, sub_type: str,
                    subtask_index: int, is_continuation: bool,
                    main_task: str, cont_content: str, cont_path: str) -> bool:
        """按任务属性定义循环执行各阶段 run_loop

        Returns: 
        """
        result = self._get_phases(sp_key, sub_type)
        if result is None:
            self._log(f"  ⚠️ spec.md 中未找到 {sp_key} (sub_type={sub_type}) 的阶段定义，跳过", always=True)
            return False

        phases = result['phases']
        extra_prompt = result.get('extra_prompt', '')
        if isinstance(extra_prompt, list):
            extra_prompt = "\n".join(extra_prompt)

        # 构建任务级别 extra_prompt：pretask + 任务元信息 + 历史延续信息（所有 phase 共享）
        pretask = self._build_pretask_skills()
        extra_prompt += "\n" + pretask
        extra_prompt += f"\n当前任务: {sub_task}"
        extra_prompt += f"\n任务类别: {sp_key}"
        if sub_type:
            extra_prompt += f"\n子类型: {sub_type}"
        if is_continuation:
            extra_prompt += (
                f"\n[历史任务延续] 主任务: 「{main_task}」\n"
                f"关联子任务: {cont_content}\n"
                f"关联项目路径: {cont_path}"
            )
      
        # 构建完整 system prompt（含 tools JSON、项目目录、阶段数、extra_prompt）
        task_tools = get_tools_excluding("start_task")
        system_prompt = (
            self.prompts.task_prompt_exclude_tools
            + "\n"
            + json.dumps(task_tools, ensure_ascii=False)
        )
        if extra_prompt:
            system_prompt += "\n" + extra_prompt

        system_prompt+=f"\n\n当前项目目录: {self.proj_path}\n所有文件操作请在此目录下进行。"

        # print(f"[DEBUG _run_landscape] system_prompt 长度: {len(system_prompt)}, system_prompt 部分: {system_prompt}")
    
        print(f"[DEBUG _run_landscape] system_prompt 长度: {len(system_prompt)}, extra_prompt 部分: {extra_prompt[:200]}...")

        # 预构建各 phase 消息（仅包含当前阶段名 + [M] 内容 + [P] 内容）
        phase_msgs = []
        for phase_idx, phase in enumerate(phases):
            phase_name = phase['name']
            phase_msg_items = phase.get('phase_msg', [])
            phase_prompt_items = phase.get('phase_prompt', [])

            lines_p = [f"当前阶段: {phase_name}"]
            for item in phase_msg_items:
                lines_p.append(item)
            full_msg = '\n'.join(lines_p)

            phase_msgs.append({
                "name": phase_name,
                "msg": full_msg,
                "phase_prompt": '\n'.join(phase_prompt_items) if phase_prompt_items else "",
            })
            print(f"[DEBUG _run_landscape] phase '{phase_name}': phase_prompt='{phase_msgs[-1]['phase_prompt']}', msg={full_msg[:100]}")
            self._log(f"  阶段 {phase_idx+1}/{len(phases)}: {phase_name}")

        result = self._run_loop(phase_msgs[0]['msg'], subtask_index, phases=phase_msgs, extra_prompt=system_prompt)

        print(self.task_llm.dump_history())
        self._log(f"\n{'='*60}")
        self._log(f"LLM 交互次数: {self.task_llm.call_count}")
        self._log(f"执行日志: {self.logger.path}")
        self._log(f"任务状态: {self.log_dir}/task_state.json")
 
        self._save_task_state()
        return result

    def _get_phases(self, task_type_key: str, sub_type: str = ""):
        """从 TaskAttributeManager 获取指定 task type 的阶段列表

        Returns:
            {"phases": [{"name": ..., "phase_prompt": [...], "phase_msg": [...]}], "extra_prompt": "..."}
            或 None（未找到匹配项或 sub_type 不匹配）
        """
        if not hasattr(self, '_attr_mgr'):
            from task_attribute_manager import TaskAttributeManager
            json_path = os.path.join(self.spc_dir, "spec.json")
            self._attr_mgr = TaskAttributeManager(json_path)
        result = self._attr_mgr.get_phases(task_type_key, sub_type)
        if result is None:
            self._log(
                f"  ⚠️ 任务子类型 '{sub_type}' 不在大类 '{task_type_key}' 的可用子类型中",
                always=True,
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

        executor = ToolExecutor(self.proj_path, logger=self.logger, agent=self)

        pretask = self._build_pretask_skills() + self._build_pretask_prjdocs()

        prompt =  self.prompts.chat_prompt+ pretask 


        msg=  user_message
        # 初始化 StageProgress（chat 模式无预定义阶段，LLM 通过 update_plan 动态创建）
        self._stage_progress = StageProgress()
        rounds = 0
        while True:
            rounds += 1
            if rounds > self.max_rounds:
                return {"judge": "false", "content": "超过最大调用次数"}
            
            result = self.chat_llm.chat_with_tools(prompt, msg, TOOLS, use_memory=True)
           
            if result["type"] == "tool_calls":
                responses = []
                for i, call in enumerate(result["calls"]):
                    exec_result = executor.execute(call["name"], call["args"])
                    self.chat_llm.submit_tool_result(call["id"], str(exec_result))
                    if isinstance(exec_result, dict) and exec_result.get("type") == "finish":
                        summary = exec_result["summary"]
                        if summary:
                            # self._log(f"\n 🏆： {summary}",always=True)
                            return {"judge": "true", "content": summary}

                    responses.append(str(exec_result))
                # 总结给用户
                summary = "\n".join(responses) if isinstance(responses, list) else str(responses)
                msg=summary
                continue
            else:
                content_text = result.get("content", "")
                # if content_text:
                #     self._log(f"\n  🤖: {content_text}\n",always=True)
                return {"judge": "true", "content": content_text}

    def _run_loop(self, task_message: str, subtask_index: int | None = None,
                  phases: list | None = None,
                  extra_prompt: str = "") -> dict:
        """工具调用模式执行循环。
        当前子任务的某个阶段在此处执行
        用 chat_with_tools 替代 IMP_FORMAT JSON 流程。
        LLM 通过 finish 工具标记完成/失败。
        当 phases 传入时，finish 成功后自动切换到下一阶段提示词，
        在同一对话中继续执行。

        Returns: {"judge": str, "content": str}
        """

        executor = ToolExecutor(self.proj_path, logger=self.logger, agent=self)

        self._log(f"工作目录proj: {self.proj_path}")

        max_rounds = self.max_rounds
        task_tools = get_tools_excluding("start_task")
        
        # system prompt 预构建完整，通过 extra_prompt 传入
        base_prompt = extra_prompt

        # 构建初始 prompt（含第一个 phase 的 phase_prompt）
        def _build_phase_prompt(phase):
            pp = phase.get('phase_prompt', '')

            if pp:
                temp= f"\n## 当前阶段({phase.get('name', '')})提示\n" + pp
            else:
                temp=f"\n## 当前阶段({phase.get('name', '')})\n"   
                
            temp += ("\n- 开始前先调用 update_plan 规划本阶段执行步骤。"
                    "\n- 每个步骤完成后及时更新状态。"
                    "\n- 所有步骤完成后调用 finish 结束本阶段。")

            return temp


        prompt = base_prompt
        if phases:
            prompt += _build_phase_prompt(phases[0])
            # 初始化 StageProgress
            stage_names = [p["name"] for p in phases]
            self._stage_progress = self.task_manager.load_stage_progress(stage_names)
            # 将当前阶段计划作为 msg 传给 LLM
            plan_msg = (
                f"当前阶段: {phases[0]['name']}\n"
                f"所有阶段进度:\n{self._stage_progress.format_status()}\n"
                f"请先调用 update_plan 规划「{phases[0]['name']}」阶段的详细步骤。"
            )
            msg = task_message + "\n\n" + plan_msg if task_message else plan_msg
            self._log(f"[PHASE] prompt={len(prompt)}chars | msg= {msg}", always=True)


        self.task_manager.add_conversation_entry(
            "user",
            f"子任务 [{subtask_index}] user message:" + task_message,
            subtask_index)

        msg = task_message
        phase_idx = 0
        stat=0


        for num in range(max_rounds):
            result = self.task_llm.chat_with_tools(prompt, msg, task_tools)
            reasoning = result.get("reasoning_content", "")
            if reasoning:
                self._log(f"\n\033[90m 💭 {reasoning[:500]}{'...(截断)' if len(reasoning) > 500 else ''}\033[0m", always=True)
            content_text = result.get("content", "")
            if content_text:
                stat=stat+1
                self._log(f"\n📩{content_text}")

            if result["type"] == "tool_calls":
                phase_changed = False
                for call in result["calls"]:
                    self._log(f"共: {max_rounds}, 第 {num} 轮  🔧 {call['name']}({call['args']})")
                    exec_result = executor.execute(call["name"], call["args"])

                    if isinstance(exec_result, dict) and exec_result.get("type") == "finish":
                        # 提交 tool 响应，满足协议要求
                        self.task_llm.submit_tool_result(call["id"], str(exec_result))

                        if not exec_result["success"]:
                            self.task_manager.set_subtask_result(
                                subtask_index, "false", exec_result["summary"])
                            self.task_manager.set_subtask_status(
                                subtask_index, SubTaskStatus.FAILED)
                            name = phases[phase_idx]['name'] if phases else ''
                            self._log(f"\n  {self._stage_progress.format_status()}", always=True)
                            self._update_task_list() 
                            self._save_task_state()
                            return {"judge": "false", "content": exec_result["summary"]}

                        if phases and phase_idx < len(phases):
                            self.task_manager.add_conversation_entry(
                                "agent",
                                f"子任务 [{subtask_index}] {phases[phase_idx]['name']} :{phases[phase_idx]['msg']} 完成",
                                subtask_index=subtask_index)
                            self._save_task_state()

                        if phases and phase_idx + 1 < len(phases):
                            phase_idx += 1
                            self._log(f"  → 进入 {phases[phase_idx]['name']}")
                            # 重建 prompt 以包含新 phase 的 config_prompt
                            prompt = base_prompt + _build_phase_prompt(phases[phase_idx])
                            # 更新 msg 以包含新阶段计划
                            plan_msg = (
                                f"进入新阶段: {phases[phase_idx]['name']}\n"
                                f"所有阶段进度:\n{self._stage_progress.format_status()}\n"
                                f"请先调用 update_plan 规划「{phases[phase_idx]['name']}」阶段的详细步骤。"
                            )
                            msg = plan_msg

                            self._save_task_state()
                            self._log(f"[PHASE] 切换后 prompt={len(prompt)}chars | msg= {msg}", always=True)
                            self._log(f"[PHASE] prompt= {prompt}", always=True)

                            phase_changed = True
                        else:
                            self.task_manager.set_subtask_status(
                                subtask_index, SubTaskStatus.COMPLETED)
                            self._log(f"\n阶段总结: {exec_result['summary']}")
                            self._log(f"\nLLM 交互次数: {self.task_llm.call_count}")
                            self.task_manager.add_conversation_entry(
                                "assistant", f"总结: {exec_result["summary"]}",
                                subtask_index)
                            self._save_task_state()
                            return {"judge": "true", "content": exec_result["summary"]}
                    else:
                        self.task_llm.submit_tool_result(call["id"], str(exec_result))

                    self._log(f"     → {str(exec_result)[:500]}")

                # 收敛压力：根据已消耗轮次注入提示
                rounds_used = num + 1
                convergence = ''
                if rounds_used >= max_rounds * 0.5:
                    convergence = (
                        f'\n[⚠ 已消耗 {rounds_used}/{max_rounds} 轮，'
                        f'如当前任务无法在剩余轮次内完成，请调用 finish(success=False) 结束。]'
                    )
                elif rounds_used >= max_rounds * 0.25:
                    convergence = (
                        f'\n[{rounds_used}/{max_rounds} 轮，请精简操作、避免反复读写。]'
                    )

                if phase_changed:
                    msg = phases[phase_idx]['msg']
                    if convergence:
                        msg += convergence
                elif convergence:
                    base = msg.split('\n[')[0] if '\n[' in msg else msg
                    msg = base + convergence

            elif result["type"] == "error":
                self._log(f"\n❌ API错误: {result.get('message', '')}\n", always=True)
                return {"judge": "false", "content": result.get("message", "API错误")}
            
            continue


        return {"judge": "false", "content": f"达到最大轮次 ({max_rounds})，任务未完成"}

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
        wd = self.work_dir
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

    def _classify_with_history(self, user_task: str, enable_history: bool = True) -> dict | None:
        """阶段0：任务分解（统一走 TaskClassifier.classify）

        enable_history=True 时加载历史上下文并传给 TaskClassifier。
        """
      
        tc = TaskClassifier(self.task_llm, self.prompts)

        history_ctx = ""
        if enable_history:
            history_ctx = TaskManager.build_history_context(self.task_dir)

        classification = tc.classify(user_task,
                                     enable_history=enable_history,
                                     history_ctx=history_ctx)
        if classification is None:
            return None

  
        return classification

    def _save_task_state(self):
        """将 task_manager 状态序列化到 task_state.json"""

        try:
            save_path = getattr(self, '_task_state_path',
                                os.path.join(self.task_dir, "task_state.json"))
            self.task_manager.save(save_path)
        except Exception:
            pass

    def _resolve_subtask_dir(self, subtask_index: int, dir_from: str,
                             subtask_content: str = "",
                             is_continuation: bool = False,
                             related_project_path: str = "") -> str:
        """解析子任务工作目录

        dir_from: temp → workspace/temp/ / reuse → 复用 / [建议名] → 交互输入
        """

        if dir_from.startswith("[") and dir_from.endswith("]"):
            # 带建议名的新建：提示用户输入，10s 超时使用建议名
            suggested = dir_from[1:-1].strip()
            if not suggested:
                self._log(f"\n❌ 子任务 [{subtask_index}] dir_from 建议名为空", always=True)
                raise ValueError(f"dir_from 建议名为空: {dir_from}")

            proj_name = suggested  # 默认值
            if sys.stdin.isatty() and threading.current_thread() is threading.main_thread():
                import signal
                timed_out = [False]
                def _alarm(signum, frame):
                    timed_out[0] = True
                old = signal.signal(signal.SIGALRM, _alarm)
                signal.alarm(10)
                try:
                    user_input = input(
                        f"\n📁 子任务 [{subtask_index}] 请输入项目目录名 "
                        f"[{suggested}]: "
                    ).strip()
                    if user_input:
                        proj_name = user_input
                except (EOFError, KeyboardInterrupt):
                    pass
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old)
                if timed_out[0]:
                    self._log(f"\n⏰ 超时，使用建议名称: {suggested}", always=True)

            proj_path = os.path.join(self.work_dir, proj_name)
            os.makedirs(proj_path, exist_ok=True)
            docs_dir = os.path.join(proj_path, "docs")
            os.makedirs(docs_dir, exist_ok=True)

        elif dir_from == "reuse":
            if is_continuation and related_project_path:
                proj_name = os.path.basename(related_project_path.rstrip("/")) or "workspace"
                proj_path = related_project_path
            else:
                proj_name = "workspace"
                proj_path = self.work_dir
            docs_dir = os.path.join(proj_path, "docs")
            os.makedirs(docs_dir, exist_ok=True)

        else:
            proj_name = "temp"
            proj_path = os.path.join(self.work_dir, "temp")
            os.makedirs(proj_path, exist_ok=True)
            docs_dir = os.path.join(proj_path, "docs")
            os.makedirs(docs_dir, exist_ok=True)


        self.task_manager.set_subtask_project(subtask_index, proj_name, proj_path, docs_dir)

        self.proj_path = proj_path
        self.work_dir = proj_path
        self.docs_dir = docs_dir

        self._log(f"   目录策略: {dir_from} → {proj_path}")
        return proj_path

    def _update_task_list(self):
        """更新 task_list.json 任务索引，保留最近 50 条"""

        try:
            list_path = os.path.join(self.task_dir, "task_list.json")
            task_list = []
            if os.path.exists(list_path):
                try:
                    with open(list_path, 'r', encoding='utf-8') as f:
                        task_list = json.load(f)
                except Exception:
                    task_list = []

            state_path = getattr(self, '_task_state_path', '')
            existing = None
            for i, t in enumerate(task_list):
                if t.get("state_file") == state_path:
                    existing = i
                    break

            entry = {
                "main_task": self.task_manager.main_task.task if self.task_manager.main_task else "",
                "status": self.task_manager.main_task.status.value if self.task_manager.main_task else "",
                "created_at": self.task_manager.main_task.created_at if self.task_manager.main_task else "",
                "completed_at": self.task_manager.main_task.completed_at if self.task_manager.main_task else "",
                "state_file": state_path,
                "subtasks_count": len(self.task_manager.subtasks),
                "completed_count": sum(1 for s in self.task_manager.subtasks
                                      if s.status == SubTaskStatus.COMPLETED),
            }
            if existing is not None:
                task_list[existing] = entry
            else:
                task_list.append(entry)

            if len(task_list) > 50:
                task_list = task_list[-50:]

            with open(list_path, 'w', encoding='utf-8') as f:
                json.dump(task_list, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _init_log(self):
        """初始化日志文件、日志器注入、task_state 路径"""
        os.makedirs(self.log_dir, exist_ok=True)
        self.logger.init(self.log_dir)
        self.logger.write(f"模型: {self.task_llm.provider_name} / {self.task_llm.model}")
        if self.auth:
            self.auth.logger = self.logger
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._task_state_path = os.path.join(self.task_dir, f"task_{ts}_state.json")
