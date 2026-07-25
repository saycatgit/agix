"""Executor —— 任务执行器：扫描任务文件夹，按计划时间调度执行子任务"""

import os
import time
import threading
import queue

from llm_client import LLMClient
from meta import TaskField, MsgType, MsgField, MsgStyle
from prompts import Prompts
from task_manager import TaskManager, SubTaskStatus
from logger import Logger
from stage_progress import StageProgress
from utils import Utils
from tools import ToolExecutor, get_tools_excluding


class Executor:
    """任务执行器

    职责:
        1. 扫描 task_dir 中的子任务文件夹（Planner 产出）
        2. 按计划时间调度执行
        3. 管理执行生命周期：_init_subtask_prj → _run_loop（project_path 由 Planner 在规划阶段赋值）
    """

    def __init__(self, agent, task_dir: str, eqm=None):
        self.agent = agent
        self.task_dir = task_dir
        self.llm = LLMClient(agent.config.llm, logger=agent.logger,
                             log_history=agent.config.log.history,user="executor")
        self.eqm = eqm
        self.prompts = Prompts(agent.config.paths.task_config_file_path)
        self._stopped = threading.Event()
        self._thread = None
        self._attr_mgr = None

    # ── 公共 API ──

    def start(self):
        """启动后台扫描线程"""
        self._stopped.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        """停止扫描线程"""
        self._stopped.set()

    # ── 内部：扫描与调度 ──

    def _worker(self):
        """后台工作线程：轮询任务文件夹，执行到期子任务"""
        Logger.mark_thread("executor")
        while not self._stopped.is_set():
            ready = self._scan_ready_tasks()
            for tm_path in ready:
                try:
                    tm = TaskManager.load(tm_path)
                except Exception:
                    continue
                if tm and tm.subtask:
                    self._log(f"{'='*30}")
                    self._execute_subtask(tm)
            time.sleep(1)

    def _scan_ready_tasks(self) -> list:
        """扫描 task_dir，返回到期且状态为 PENDING 的任务文件路径列表"""
        ready = []
        if not os.path.isdir(self.task_dir):
            return ready
        for name in sorted(os.listdir(self.task_dir)):
            if not name.startswith("task_") or not name.endswith("_state.json"):
                continue
            tm_path = os.path.join(self.task_dir, name)
            try:
                tm = TaskManager.load(tm_path)
            except Exception:
                continue
            if tm is None or tm.subtask is None:
                continue
            if tm.subtask.status in (SubTaskStatus.PENDING, None) and tm.is_execution_time_reached():
                # 一次性任务只允许执行一次（counter==0 表示从未执行过）
                # if not tm.subtask.is_periodic and tm._periodic_counter > 0:
                #     continue
                ready.append(tm_path)
        return ready

    # ── 内部：子任务执行 ──

    def _execute_subtask(self, task_manager: TaskManager):
        """执行单个子任务：解析目录 → 初始化 → run_loop"""
        sub = task_manager.subtask
        if sub is None:
            return

        if not sub.project_path:  # planner 应已在规划阶段赋值，空值视为异常
            self._log(f"  ⚠️ project_path 为空，跳过执行")
            return

        task_manager.set_subtask_status(SubTaskStatus.IN_PROGRESS)
        task_manager.save()

        sub_detail = sub.sub_task_detail or sub.sub_task_name or "后台任务"
        if self.eqm:
            self.eqm.send_display(f"🚀 开始执行: {sub_detail}", mode="task")

        self.llm.history.clear()
        self.llm.init_task_counters()

        system_prompt = self._init_subtask_prj(task_manager)
        if system_prompt is None:
            task_manager.set_subtask_result("false", "子任务初始化失败")
            task_manager.set_subtask_status(SubTaskStatus.FAILED)
            task_manager.save()
            if self.eqm:
                self.eqm.send_user_input(f"❌ 初始化失败: {sub_detail}\n\n这是任务模式的任务执行结果，进行总结分析展示给用户，等待用户下一步指示", mode="chat")
            return

        result = self._run_loop(task_manager, base_prompt=system_prompt)

        judge = result.get(TaskField.JUDGE, "false")
        content = result.get("content", "")
        if self.eqm:
            icon = "✅" if judge == "true" else "❌"
            self.eqm.send_user_input(f"{icon} 执行完成: {sub_detail}\n{content}\n\n这是任务模式的任务执行结果，进行总结分析展示给用户，等待用户下一步指示", mode="chat")

        task_manager.save_plan_steps(task_manager._stage_progress)
        task_manager.set_subtask_result(
            judge,
            content,
        )
        task_manager.increment_periodic_counter()
        task_manager.save()

    # ── 内部：子任务初始化 ──

    def _init_subtask_prj(self, task_manager: TaskManager) -> str | None:
        """初始化子任务项目：确定 phases、构建 system_prompt、加载记忆"""
        sub = task_manager.subtask
        if sub is None:
            self._log("  ⚠️ 子任务未找到，跳过")
            return None

        self._init_task_memory(task_manager)

        if sub.plan_steps:
            extra_prompt_cfg = sub.extra_prompt
        else:
            result = self._get_phases_prompt_from_config(sub.task_type, sub.task_sub_type)
            if result is None:
                self._log(f"  ⚠️ spec.md 中未找到 {sub.task_type} (sub_type={sub.task_sub_type}) 的阶段定义，跳过")
                return None
            phases = result["phases"]
            extra_prompt_cfg = result.get("extra_prompt", "")
            if isinstance(extra_prompt_cfg, list):
                extra_prompt_cfg = "\n".join(extra_prompt_cfg)
            task_manager.set_subtask_extra_prompt(extra_prompt_cfg)
            task_manager.set_subtask_phase_msgs(phases)
            for phase_idx, phase in enumerate(phases):
                self._log(f"  阶段 {phase_idx+1}/{len(phases)}: {phase['name']}")

        pretask = Utils.build_pretask_skills(self.agent.skills_dir)
        extra_prompt_add = "\n" + pretask
        extra_prompt_add += "\n# 当前项目：\n"
        extra_prompt_add += f"当前任务: {sub.sub_task_detail}\n"
        extra_prompt_add += f"任务类别: {sub.task_type}\n"
        if sub.task_sub_type:
            extra_prompt_add += f"子类型: {sub.task_sub_type}\n"
        extra_prompt_add += f"当前项目目录: {sub.project_path}\n所有文件操作请在此目录下进行。\n"
        extra_prompt = extra_prompt_add + extra_prompt_cfg + "\n"
        extra_prompt += (
            "- 任务需要分阶段分步骤规划完成，禁止忽略或者删除已经存在的阶段及其对应的步骤.\n"
            "- 可根据需求在已经存在的阶段和对应的步骤前面或者后面新增阶段及步骤\n"
            "- 如果完成该任务缺少必要的阶段和步骤，先调用 update_plan总体规划，然后分步执行。\n"
            "- 每个小步骤完成后及时更新状态。\n"
            "- 所有阶段步骤完成后调用 finish 结束本任务。\n"
        )

        system_prompt = self.prompts.task_prompt_exclude_tools
        if extra_prompt:
            system_prompt += "\n" + extra_prompt

        self._log(f"[DEBUG] system_prompt 长度: {len(system_prompt)}")
        return system_prompt

    def _get_phases_prompt_from_config(self, task_type_key: str, sub_type: str = ""):
        """从 TaskAttributeManager 获取指定 task type 的阶段列表"""
        if self._attr_mgr is None:
            from task_attribute_manager import TaskAttributeManager
            json_path = self.agent.config.paths.task_config_file_path
            self._attr_mgr = TaskAttributeManager(json_path)
        result = self._attr_mgr.get_phases_prompt_from_config(task_type_key, sub_type)
        if result is None:
            self._log(
                f"  ⚠️ 任务子类型 '{sub_type}' 不在大类 '{task_type_key}' 的可用子类型中"
            )
        return result

    def _init_task_memory(self, task_manager: TaskManager):
        """初始化任务模式记忆：设置 memory_file，有快照则加载"""
        sub = task_manager.subtask
        if not sub:
            return
        fpath = os.path.join(sub.project_path, ".memory", "memory.jsonl")
        self.llm.set_memory_file(fpath)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        if not os.path.exists(fpath):
            with open(fpath, "w") as _:
                pass
        task_manager.set_subtask_llm_context_info("memory.jsonl")
        if task_manager._save_path:
            task_manager.save()
        if os.path.exists(fpath):
            self.llm.load_memory()
            if self.llm.history:
                self._log(f"  📝 从快照恢复 LLM 上下文 ({len(self.llm.history)} 条消息)")

    # ── 内部：执行循环 ──

    def _run_loop(self, task_manager: TaskManager, base_prompt: str = "") -> dict:
        """工具调用模式执行循环。当前子任务的某个阶段在此处执行。

        LLM 通过 finish 工具标记完成/失败。
        当 phases 传入时，finish 成功后自动切换到下一阶段提示词。

        Returns: {"judge": str, "content": str}
        """
        sub = task_manager.subtask
        max_rounds = self.agent.config.execution.max_rounds

        executor = ToolExecutor(
            sub.project_path, logger=self.agent.logger,
            agent=self.agent, eqm=self.eqm, mode="task", task_manager=task_manager,
        )

        self._log(f"工作目录proj: {sub.project_path}")

        task_tools = get_tools_excluding("start_task")

        if sub and sub.plan_steps:
            try:
                task_manager._stage_progress = StageProgress.from_dict(sub.plan_steps)
            except Exception:
                task_manager._stage_progress = StageProgress()
        elif sub and sub.phase_msgs:
            task_manager._stage_progress = task_manager.load_stage_progress(sub.phase_msgs)
        elif sub:
            task_manager._stage_progress = StageProgress()

        status = task_manager._stage_progress.format_status()
        msg_base=f"# 当前任务: {sub.sub_task_detail}\n"

        periodic_hint = ""
        if task_manager.is_periodic():
            periodic_hint = "⚠️ 此为周期任务，请先用 update_plan 重置各个阶段步骤为未执行状态，再重新执行。\n"

        msg = (
            f"# {msg_base}\n\n{status}\n\n"
            f"如果阶段或步骤缺失以至不满足当前子任务要求，请先用update_plan完善相应内容\n"
            f"{periodic_hint}"
            f"禁止删除已经存在的阶段和步骤，仅可增加\n"
            f"执行完调用finish结束"
        )

        self._log(f"[PHASE] prompt={len(base_prompt)}chars | msg= {msg}")

        for num in range(max_rounds):


            drained = ""
            control_action = None
            if self.eqm:
                try:
                    while True:
                        m = self.eqm.to_task_queue.get_nowait()
                        if m.get(MsgField.TYPE) == MsgType.USER_INPUT:
                            drained += m.get(MsgField.CONTENT, "") + "\n"
                        elif m.get(MsgField.TYPE) == MsgType.CONTROL:
                            control_action = m.get(MsgField.CONTENT, "")
                            if control_action == "stop":
                                break
                except queue.Empty:
                    pass
                if control_action == "end":
                    self.eqm.send_display("⏹ 已结束", mode="task")
                    return TaskField.RET_JSON_FALSE("用户结束任务")
                if control_action == "stop":
                    self.eqm.send_display("⏸ 已暂停", mode="task")
                    while True:
                        m = self.eqm.to_task_queue.get()
                        if m.get(MsgField.TYPE) == MsgType.CONTROL:
                            a = m.get(MsgField.CONTENT, "")
                            if a == "end":
                                self.eqm.send_display("⏹ 已结束", mode="task")
                                return TaskField.RET_JSON_FALSE("用户结束任务")
                        elif m.get(MsgField.TYPE) == MsgType.USER_INPUT:
                            drained += m.get(MsgField.CONTENT, "") + "\n"
                            break
            if drained.strip():
                msg = f"【用户新消息】\n{drained.strip()}\n\n{msg}"

            result = self.llm.chat_with_tools(base_prompt, msg, task_tools)

            reasoning = result.get("reasoning_content", "")
            thinking_enabled = self.agent.config.execution.thinking
            if reasoning and thinking_enabled:
                print(f"[debug] model={self.agent.config.llm.model}, reasoning={len(reasoning)} chars")
                if self.eqm:
                    sentences = reasoning.split("。")
                    for s in sentences:
                        s = s.strip()
                        if s:
                            self.eqm.send_display(s, mode="task", style=MsgStyle.THINKING)

            content_text = result.get("content", "")
            if content_text:
                self._log(f"\n📩{content_text}")

            if result["type"] == "tool_calls":
                for call in result["calls"]:
                    self._log(f"共: {max_rounds}, 第 {num} 轮  🔧 {call['name']}({call['args']})")
                    exec_result = executor.execute(call["name"], call["args"])

                    if isinstance(exec_result, dict) and exec_result.get("type") == "finish":
                        self.llm.submit_tool_result(call["id"], str(exec_result))

                        if not exec_result["success"]:
                            task_manager.set_subtask_result("false", exec_result["summary"])
                            task_manager.set_subtask_status(SubTaskStatus.FAILED)
                            self._log(f"\n  {task_manager._stage_progress.format_status()}")
                            return TaskField.RET_JSON_FALSE(exec_result["summary"])

                        task_manager.set_subtask_status(SubTaskStatus.COMPLETED)
                        self._log(f"\n任务总结: {exec_result['summary']}")
                        return TaskField.RET_JSON_TRUE(exec_result["summary"])
                    else:
                        self.llm.submit_tool_result(call["id"], str(exec_result))

                    self._log(f"     → {str(exec_result)[:500]}")
                msg = f"本轮完成 {len(result['calls'])} 个工具调用"

                rounds_used = num + 1
                convergence = ""
                if rounds_used >= max_rounds * 0.5:
                    convergence = (
                        f"\n[⚠ 已消耗 {rounds_used}/{max_rounds} 轮，"
                        f"如当前任务无法在剩余轮次内完成，请调用 finish(success=False) 结束。]"
                    )
                elif rounds_used >= max_rounds * 0.25:
                    convergence = (
                        f"\n[{rounds_used}/{max_rounds} 轮，请精简操作、避免反复读写。]"
                    )

                if convergence:
                    base = f"所有阶段进度:\n{task_manager._stage_progress.format_status()}"
                    msg = base + "\n" + convergence

            elif result["type"] == "error":
                self._log(f"\n❌ API错误: {result.get('message', '')}\n")
                return TaskField.RET_JSON_FALSE(result.get("message", "API错误"))
            elif result["type"] == "text":
                pass
            continue

        return TaskField.RET_JSON_FALSE(f"达到最大轮次 ({max_rounds})，任务未完成")

    # ── 辅助 ──

    def _log(self, msg: str):
        self.agent.logger.log(msg)


__all__ = ["Executor"]
