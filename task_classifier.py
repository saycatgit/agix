"""任务分类器 —— 对用户任务进行分解归类"""


class TaskClassifier:
    """任务分类器

    职责:
        接收用户原始任务描述，调用 LLM 进行语义分析，
        将复杂任务拆解为按序执行的子任务列表 (orchestrate)。
        每个子任务标注 type (开发类/调试类/文本类/其他) 和 sub_type。

    enable_history / history_ctx:
        启用时使用 combined_classify prompt 并拼接历史上下文，
        否则使用 plan_classify prompt 做纯分解。
    """

    def __init__(self, llm_client, prompts):
        self.llm = llm_client
        self.prompts = prompts

    def classify_with_history(self, user_task: str, task_dir: str,
                               enable_history: bool = True) -> dict | None:
        """分类任务，自动构建历史上下文"""
        history_ctx = ""
        if enable_history:
            from task_manager import TaskManager
            history_ctx = TaskManager.build_history_context(task_dir)
        return self.classify(user_task,
                             enable_history=enable_history,
                             history_ctx=history_ctx)

    def classify(self, user_task: str,
                 enable_history: bool = False,
                 history_ctx: str = "") -> dict:
        """对用户任务进行分类并拆解为子任务

        Args:
            user_task: 用户输入的原始任务描述
            enable_history: 是否启用历史任务关联
            history_ctx: 历史任务上下文文本（enable_history=True 时生效）

        Returns:
            dict with keys:
                main_task (str): 总任务描述
                orchestrate (list): 子任务列表，每项含 sub_task/type/sub_type
            失败时返回 None
        """
        if enable_history and history_ctx:
            system_prompt = (self.prompts.combined_classify)
            task_input = history_ctx + "\n\n## 新任务\n" + user_task
        else:
            system_prompt = (self.prompts.plan_classify)
            task_input = user_task

        result = self.llm.chat_json(system_prompt, task_input, use_memory=False)

        if "parse_error" in result:
            return None
        return result


__all__ = ["TaskClassifier"]
