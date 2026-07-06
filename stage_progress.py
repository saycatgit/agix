"""阶段进度管理 — StageProgress 类。"""

# fmt: off
# ── 阶段进度管理 ──

STATUS_ICONS = {
    "pending": "□", "in_progress": "⏳", "completed": "✅", "failed": "❌",
}

class StageProgress:
    """管理当前子任务所有阶段的步骤进度。

    每个阶段（phase_name）对应一个步骤列表，由 LLM 通过 update_plan 工具规划。
    stage 来源 == spec.json 中的 phase_name，step 来源 == LLM。

    使用方式:
        sp = StageProgress(["需求分析", "代码实现及测试", "其他要求"])
        sp.init_stage("需求分析", [{"step": "...", "status": "pending"}, ...])
        sp.update_steps("需求分析", [{"step": "...", "status": "completed"}, ...])
        sp.is_stage_complete("需求分析")  # -> bool
        sp.format_status()               # -> 可打印的状态文本
    """

    VALID_STATUSES = {"pending", "in_progress", "completed", "failed"}

    def __init__(self, stage_names: list[str] | None = None):
        """初始化所有阶段。stage_names=None 时从空开始，LLM 通过 update_plan 动态添加阶段。"""
        self._stages: dict[str, list[dict]] = {name: [] for name in stage_names} if stage_names else {}

    def init_stage(self, stage_name: str, steps: list[dict] | None = None):
        """初始化某个阶段的步骤列表。通常在每个 stage 开始执行前调用。"""
        if stage_name not in self._stages:
            self._stages[stage_name] = []
        if steps is None:
            steps = []
        for s in steps:
            if s.get("status") not in self.VALID_STATUSES:
                s["status"] = "pending"
        self._stages[stage_name] = steps

    def update_steps(self, stage_name: str, steps: list[dict]) -> bool:
        """更新某个阶段的步骤列表。LLM 通过 update_plan 工具调用。

        steps 中每项包含 {"step": "描述", "status": "pending|in_progress|completed|failed"}
        不传的步会被覆盖。
        """
        if stage_name not in self._stages:
            self._stages[stage_name] = []
        for s in steps:
            if s.get("status") not in self.VALID_STATUSES:
                s["status"] = "pending"
        self._stages[stage_name] = steps
        return True

    def is_stage_complete(self, stage_name: str) -> bool:
        """判断某个阶段的所有步骤是否都已完成或失败。"""
        steps = self._stages.get(stage_name, [])
        if not steps:
            return False
        return all(s["status"] in ("completed", "failed") for s in steps)

    def get_stage_steps(self, stage_name: str) -> list[dict]:
        """获取某个阶段的步骤列表（安全拷贝）。"""
        return list(self._stages.get(stage_name, []))

    def format_status(self) -> str:
        """以人类可读格式返回所有阶段的进度状态。"""
        lines = []
        for name, steps in self._stages.items():
            lines.append(f"## {name}")
            if not steps:
                lines.append("  (无步骤)")
                continue
            for i, s in enumerate(steps):
                icon = STATUS_ICONS.get(s.get("status", "pending"), "□")
                first = "  └" if i == 0 else "   "
                lines.append(f"{first} {icon} {s['step']}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, list[dict]]:
        """序列化为 dict。"""
        return dict(self._stages)

    @staticmethod
    def from_dict(data: dict[str, list[dict]]) -> "StageProgress":
        """从 dict 反序列化。"""
        sp = StageProgress(list(data.keys()))
        sp._stages = dict(data)
        return sp
