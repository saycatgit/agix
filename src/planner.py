"""Planner —— 任务规划器：分类拆解 + 生成任务文件"""
import os
import json
from datetime import datetime
from llm_client import LLMClient
from meta import TaskField
from prompts import Prompts
from task_manager import SubTaskRecord, SubTaskStatus, TaskManager


class Planner:
    """任务规划器

    职责:
        1. 调用 LLM 将用户任务拆解为子任务列表 (orchestrate)
        2. 对每个子任务创建 TaskManager + SubTaskRecord 并生成任务文件到 task_dir

    与旧 TaskClassifier 的区别：
        Planner 不只做分类，还负责将分类结果持久化为任务文件，供 Executor 扫描执行。
    """

    def __init__(self, config, logger=None, eqm=None):
        self.config = config
        self.llm = LLMClient(config.llm, logger=logger,
                             log_history=config.log.history)
        self._eqm = eqm
        self.prompts = Prompts(config.paths.task_config_file_path)

    def classify(self, user_task: str,
                 enable_history: bool = False,
                 history_ctx: str = "") -> dict:
        """对用户任务进行分类并拆解为子任务

        Returns:
            dict with key 'orchestrate' (list)，失败返回 {'parse_error': ...} 或 RETURN_FALSE 标记
        """
        task_input=" "
        if enable_history and history_ctx:
            system_prompt = self.prompts.combined_classify
            task_input = history_ctx 
        else:
            system_prompt = self.prompts.plan_classify

        task_input += "\n## 用户需求:\n" + user_task+"\n 根据系统提示词对此需求分类,并以json格式输出"

        result = self.llm.chat_json(system_prompt, task_input, use_memory=False)

        if "parse_error" in result:
            return TaskField.RET_JSON_FALSE(str(result))
        return result

    def classify_with_history(self, user_task: str,
                               enable_history: bool = True) -> dict | None:
        """分类任务，自动构建历史上下文"""
        task_dir = self.config.paths.task_dir
        history_ctx = ""
        if enable_history:
            history_ctx = TaskManager.build_history_context(task_dir)
        return self.classify(user_task,
                             enable_history=enable_history,
                             history_ctx=history_ctx)

    def run(self, user_task: str,
            is_periodic: bool = False,
            period: str = "",
            enable_history: bool = True) -> dict:
        """完整规划流程：分类 → 生成任务文件

        Returns:
            dict: {"ok": bool, "task_file": str, "error": str, "subtasks": list}
        """
        task_dir = self.config.paths.task_dir
        classification = self.classify_with_history(user_task, enable_history=enable_history)
        if TaskField.IS_FALSE(classification):
            return {"ok": False, "error": f"任务分类失败: {classification}"}

        orchestrate = classification.get("orchestrate", [])
        if not orchestrate:
            return {"ok": False, "error": "任务分类结果为空"}

        subtask_records = []
        task_files = []

        for i, item in enumerate(orchestrate, 1):
            rec = SubTaskRecord.from_orchestrate_item(i, item)
            subtask_records.append(rec)

            dir_from = item.get("dir_from", "")
            related = item.get("related_task_file_name", "")

            if dir_from == "reuse" and related:
                # 复用已有 in_progress 任务文件，不新建
                related_path = os.path.join(task_dir, related)
                try:
                    tm = TaskManager.load(related_path)
                    tm.set_subtask_merge(item)
                    tm.set_subtask_status(SubTaskStatus.PENDING)
                    save_path = related_path
                except Exception:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    save_path = os.path.join(task_dir, f"task_{ts}_state.json")
                    tm = TaskManager(save_path=save_path)
                    tm.set_subtask(item)
            else:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                save_path = os.path.join(task_dir, f"task_{ts}_state.json")
                tm = TaskManager(save_path=save_path)
                tm.set_subtask(item)

            tm.set_subtask_execution_time(
                item.get("next_execution_time", "now"),
                is_periodic=item.get("is_periodic", False),
                period=item.get("period", ""),
            )
            self._resolve_project_path(item, tm)
            tm.save()
            task_files.append(save_path)

        return {"ok": True, "task_files": task_files, "subtasks": subtask_records}

    def _resolve_project_path(self, item: dict, task_manager: TaskManager):
        """根据 dir_from 决定 project_path，迁移自 executor"""
        dir_from = item.get("dir_from", "")
        work_dir = self.config.execution.config_work_dir

        if dir_from == "reuse":
            related = item.get("related_task_file_name", "")
            if related:
                related_path = os.path.join(self.config.paths.task_dir, related)
                try:
                    related_tm = TaskManager.load(related_path)
                    if related_tm and related_tm.subtask and related_tm.subtask.project_path:
                        task_manager.set_subtask_project(related_tm.subtask.project_path)
                        return
                except Exception:
                    pass
            # 兜底：reuse 失败则用 temp
            proj_path = os.path.join(work_dir, "temp")
            os.makedirs(proj_path, exist_ok=True)
            task_manager.set_subtask_project(proj_path)

        elif dir_from == "temp":
            proj_path = os.path.join(work_dir, "temp")
            os.makedirs(proj_path, exist_ok=True)
            task_manager.set_subtask_project(proj_path)

        elif dir_from.startswith("[") and dir_from.endswith("]"):
            default_name = dir_from[1:-1]

            if self.config.execution.interactive and self._eqm:
                folder_name = self._eqm.ask_user(
                    f"请输入项目文件夹名（默认: {default_name}）",
                    mode="chat",
                    timeout=self.config.execution.timeout,
                )
                if not folder_name:
                    folder_name = default_name
            else:
                folder_name = default_name

            proj_path = os.path.join(work_dir, folder_name)
            os.makedirs(proj_path, exist_ok=True)
            task_manager.set_subtask_project(proj_path)

        else:
            # 未知格式，兜底 temp
            proj_path = os.path.join(work_dir, "temp")
            os.makedirs(proj_path, exist_ok=True)
            task_manager.set_subtask_project(proj_path)


__all__ = ["Planner"]
