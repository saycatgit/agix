"""任务状态管理器

维护 Agent 任务管线的完整状态信息：
- 所有子任务的类型、内容、当前状态
- 各子任务对应的项目路径和文档目录
- Agent 与用户的问答交互历史
- 任务执行结果

可独立使用，不与现有代码耦合。
"""

from __future__ import annotations

import json, os, glob, re
from dataclasses import dataclass, field
from stage_progress import StageProgress
from datetime import datetime
from enum import Enum
from typing import Any
from meta import TaskField

# ================================================================
# 枚举定义
# ================================================================


class SubTaskStatus(Enum):
    """子任务生命周期状态

    PENDING     → 待处理
    IN_PROGRESS → 执行中
    COMPLETED   → 已完成
    FAILED      → 已失败
    SKIPPED     → 已跳过
    """
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"
    SKIPPED     = "skipped"

# ================================================================
# 数据记录
# ================================================================

@dataclass
class QAMessage:
    """单条问答记录"""
    role:      str
    content:   str
    timestamp: str = ""
    context:   str = ""



@dataclass
class SubTaskRecord:
    """子任务完整记录

    每个 orchestrate 子任务对应一条记录，追踪从分类到执行完成的全部信息。
    """
    index:          int
    sub_task_name:  str = ""
    sub_task_detail: str = ""
    task_type:      str =""
    task_sub_type:       str = ""
    llm_context_info: str = ""
    extra_prompt:    str = ""
    phase_msgs:     list = field(default_factory=list)
    status:         SubTaskStatus = SubTaskStatus.PENDING
    next_execution_time:  str = ""
    is_periodic:     bool = False
    period:          str = ""
    is_interactive:  bool = False
    dir_from:       str = ""
    related_task_file_name: str = ""
    project_path:   str = ""
    extra:          str = ""
    result_judge:   str = ""
    result_content: str = ""
    round_count:    int = 0
    messages:       list = field(default_factory=list)
    created_at:     str = ""
    completed_at:   str = ""
    plan_steps:     dict = field(default_factory=dict)  # {phase_name: [{"step":..., "status":...}]}

    @staticmethod
    def from_orchestrate_item(index: int, item: dict) -> "SubTaskRecord":
        """从 orchestrate 列表项构造记录"""
        # 解析时间字段
        first_time = item.get("next_execution_time", "now")
        is_periodic = bool(item.get("is_periodic", False))
        period = str(item.get("period", ""))
        rec = SubTaskRecord(
            index=index,
            sub_task_detail=item.get(TaskField.SUB_TASK_DETAIL, ""),
            sub_task_name=item.get(TaskField.SUB_TASK_NAME, ""),
            task_type=item.get("task_type", "其他"),
            task_sub_type=item.get("task_sub_type", ""),
            dir_from=item.get("dir_from", ""),
            related_task_file_name=item.get("related_task_file_name", ""),
            is_periodic=is_periodic,
            period=period,
            created_at=_now_iso(),
        )
        # 计算 next_execution_time
        rec.next_execution_time = _parse_execution_time(first_time)
        return rec


# ================================================================
# 任务状态管理器
# ================================================================

class TaskManager:
    """任务状态管理器

    集中维护 Agent 完整任务生命周期的状态信息，提供读写、查询、
    序列化等接口。所有修改立即生效，持久化调用 save()。
    """

    def __init__(self, save_path: str = ""):
        """初始化任务管理器。save_path 用于 save() 持久化。"""
        self._subtask: SubTaskRecord | None = None
        self._global_messages: list[QAMessage] = []
        self._conversation_log: list[dict] = []
        self._save_path = save_path
        self._stage_progress: StageProgress | None = None
        self._periodic_counter: int = 0

    # ── 子任务管理 ──

    def set_subtask(self, item: dict) -> SubTaskRecord:
        """设置（创建或替换）当前子任务记录"""
        rec = SubTaskRecord.from_orchestrate_item(1, item)
        self._subtask = rec
        return rec

    def set_subtask_merge(self, item: dict):
        """合并式设置：只在原记录字段为空时，从 item 填充，已有值不覆盖。"""
        if not self._subtask:
            self._subtask = SubTaskRecord.from_orchestrate_item(1, item)
            return

        new_rec = SubTaskRecord.from_orchestrate_item(1, item)
        merge_fields = [
            "sub_task_detail", "sub_task_name", "task_type",
            "task_sub_type", "dir_from", "related_task_file_name",
        ]
        for f in merge_fields:
            existing = getattr(self._subtask, f, "")
            if not existing:
                incoming = getattr(new_rec, f, "")
                if incoming:
                    setattr(self._subtask, f, incoming)

    def set_subtask_status(self, status: SubTaskStatus):
        """更新子任务的状态"""
        if self._subtask:
            self._subtask.status = status
            if status in (SubTaskStatus.COMPLETED, SubTaskStatus.FAILED, SubTaskStatus.SKIPPED):
                self._subtask.completed_at = _now_iso()

    def set_subtask_project(self, project_path: str):
        """设置子任务项目路径"""
        if self._subtask:
            self._subtask.project_path = project_path

    def set_subtask_docs(self, docs: dict):
        """设置子任务关联的文档路径和名称。"""
        if self._subtask:
            for k, v in docs.items():
                if isinstance(v, dict) and v.get("path"):
                    pass  # 保持接口兼容，不再按列表存储路径

    def set_subtask_result(self, judge: str, content: str, rounds: int = 0):
        """记录子任务的执行结果（成功/失败判定 + 结果摘要 + 消耗轮次）。"""
        if self._subtask:
            self._subtask.result_judge   = judge
            self._subtask.result_content = content
            self._subtask.round_count    = rounds

    def set_subtask_extra(self, extra: str):
        """设置子任务的额外元信息字段。"""
        if self._subtask:
            self._subtask.extra = extra

    def set_subtask_extra_prompt(self, extra_prompt: str):
        """设置子任务配置 extra_prompt。"""
        if self._subtask:
            self._subtask.extra_prompt = extra_prompt

    def set_subtask_phase_msgs(self, phase_msgs: list):
        """设置子任务的阶段信息列表"""
        if self._subtask:
            self._subtask.phase_msgs = phase_msgs

    def set_subtask_llm_context_info(self, info: str):
        """设置子任务的 LLM 上下文信息哈希"""
        if self._subtask:
            self._subtask.llm_context_info = info

    # ── 时间管理 ──

    def set_subtask_execution_time(self, first_time: str, is_periodic: bool = False, period: str = ""):
        """设置子任务的执行时间相关字段并计算 next_execution_time。"""
        if self._subtask:
            self._subtask.is_periodic = is_periodic
            self._subtask.period = period
            self._subtask.next_execution_time = _parse_execution_time(first_time)

    def is_execution_time_reached(self) -> bool:
        """检查子任务是否到达执行时间。无子任务或无 next_execution_time 返回 False。"""
        if not self._subtask or not self._subtask.next_execution_time:
            return False
        try:
            target = datetime.fromisoformat(self._subtask.next_execution_time)
            return datetime.now() >= target
        except (ValueError, TypeError):
            return False

    def reschedule_next_execution(self):
        """周期任务：将 next_execution_time 推进一个 period。非周期任务清空 next_execution_time。"""
        sub = self._subtask
        if not sub or not sub.is_periodic or not sub.period or not sub.next_execution_time:
            if sub and not sub.is_periodic and sub.next_execution_time:
                sub.next_execution_time = ""
            return
        try:
            current = datetime.fromisoformat(sub.next_execution_time)
            delta = _parse_duration(sub.period)
            if delta:
                next_time = current + delta
                # 跳过已过去的时间
                now = datetime.now()
                while next_time <= now:
                    next_time += delta
                sub.next_execution_time = next_time.isoformat()
                sub.status = SubTaskStatus.PENDING
        except (ValueError, TypeError):
            pass

    def update_execution_time(self, next_time_iso: str):
        """直接设置 next_execution_time（如 Planner 已计算好）。"""
        if self._subtask:
            self._subtask.next_execution_time = next_time_iso

    @property
    def subtask(self) -> SubTaskRecord | None:
        """当前子任务记录。"""
        return self._subtask

    # ── 问答记录与对话日志 ──

    def add_qa(self, role: str, content: str, context: str = ""):
        """向当前子任务添加一条问答记录"""
        msg = QAMessage(role=role, content=content, timestamp=_now_iso(), context=context)
        if self._subtask:
            self._subtask.messages.append(msg)

    def get_qa_history(self) -> list[QAMessage]:
        """获取当前子任务的问答历史"""
        return list(self._subtask.messages) if self._subtask else []

    # ── 序列化 ──

    def to_dict(self) -> dict[str, Any]:
        """导出为可 JSON 序列化的字典"""

        def _msg_to_dict(m: QAMessage) -> dict:
            return {
                "role": m.role, "content": m.content,
                "timestamp": m.timestamp, "context": m.context,
            }

        def _sub_to_dict(s: SubTaskRecord) -> dict:
            d = {
                TaskField.SUBTASK_INDEX: s.index, TaskField.SUB_TASK_DETAIL: s.sub_task_detail, "task_type": s.task_type,
                "task_sub_type": s.task_sub_type, "dir_from": s.dir_from, "status": s.status.value,
                "project_path": s.project_path,
                "result_judge": s.result_judge, "result_content": s.result_content,
                "round_count": s.round_count,
                "messages": [_msg_to_dict(m) for m in s.messages],
                "created_at": s.created_at, "completed_at": s.completed_at,
                "plan_steps": s.plan_steps,
                "phase_msgs": s.phase_msgs,
                "llm_context_info": s.llm_context_info,
                "extra_prompt": s.extra_prompt,
            }
            if s.related_task_file_name:
                d["related_task_file_name"] = s.related_task_file_name
            if s.sub_task_name:
                d[TaskField.SUB_TASK_NAME] = s.sub_task_name
            if s.is_interactive:
                d["is_interactive"] = s.is_interactive
            return d

        return {
            "subtask": _sub_to_dict(self._subtask) if self._subtask else None,
            "conversation_log": list(self._conversation_log),
            TaskField.GENERAL_MSGS: [_msg_to_dict(m) for m in self._global_messages],
            "periodic": {
                "counter": self._periodic_counter,
                "next_execution_time": self._subtask.next_execution_time if self._subtask else "",
                "is_periodic": self._subtask.is_periodic if self._subtask else False,
                "period": self._subtask.period if self._subtask else "",
            },
        }

    def save(self, path: str = ""):
        """将状态序列化到 JSON 文件"""
        p = path or self._save_path
        if not p:
            raise ValueError("save() 需要提供 path 参数")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def increment_periodic_counter(self):
        """每执行一次子任务，计数器自增 1，并推进 next_execution_time"""
        self._periodic_counter += 1
        self.reschedule_next_execution()

    def is_periodic(self) -> bool:
        """当前子任务是否为周期任务"""
        return self._subtask is not None and self._subtask.is_periodic

    @classmethod
    def load(cls, path: str) -> "TaskManager":
        """从 JSON 文件恢复 TaskManager 实例"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tm = cls(save_path=path)


        sd = data.get("subtask")
        if sd:
            rec = SubTaskRecord(
                index=sd.get(TaskField.SUBTASK_INDEX, 1),
                sub_task_detail=sd.get(TaskField.SUB_TASK_DETAIL, ""),
                task_type=sd.get(TaskField.TASK_TYPE, ""),
                sub_task_name=sd.get(TaskField.SUB_TASK_NAME, ""),
                task_sub_type=sd.get(TaskField.TASK_SUB_TYPE, ""),
                dir_from=sd.get("dir_from", ""),
                status=SubTaskStatus(sd.get("status", "pending")),
                project_path=sd.get("project_path", ""),
                extra=sd.get("extra", ""),
                result_judge=sd.get("result_judge", ""),
                result_content=sd.get("result_content", ""),
                round_count=sd.get("round_count", 0),
                messages=[QAMessage(**m) for m in sd.get("messages", [])],
                phase_msgs=sd.get("phase_msgs", []),
                llm_context_info=sd.get("llm_context_info", ""),
                extra_prompt=sd.get("extra_prompt", ""),
                related_task_file_name=sd.get("related_task_file_name", ""),
                created_at=sd.get("created_at", ""),
                completed_at=sd.get("completed_at", ""),
            )
            # 从 periodic 对象读取调度字段（兼容旧格式：字段可能仍在 subtask 顶层）
            pd = data.get("periodic", {})
            rec.next_execution_time = pd.get("next_execution_time") or sd.get("next_execution_time", "")
            rec.is_periodic = pd.get("is_periodic", sd.get("is_periodic", False))
            rec.period = pd.get("period") or sd.get("period", "")
            rec.plan_steps = sd.get("plan_steps", {})
            rec.is_interactive = sd.get("is_interactive", False)
            tm._subtask = rec

        tm._conversation_log = data.get("conversation_log", [])
        tm._global_messages = [QAMessage(**m) for m in data.get(TaskField.GENERAL_MSGS, [])]
        tm._periodic_counter = data.get("periodic", {}).get("counter", 0)
        return tm

    # ── 汇总查询 ──

    # ── 对话日志 ──

    def add_conversation_entry(self, role: str, content: str):
        """记录一条对话日志。role: user|assistant|agent"""
        self._conversation_log.append({
            "role": role,
            "content": content,
            "timestamp": _now_iso(),
        })

    def get_conversation_context(self, max_chars: int = 8000) -> str:
        """截取最近对话内容作为上下文，总量不超过 max_chars。"""
        """格式化为 LLM 可读的对话上下文"""
        if not self._conversation_log:
            return ""
        lines = ["## 当前任务对话记录"]
        total = 0
        for entry in self._conversation_log:
            line = f"[{entry['timestamp']}] {entry['role']}: {entry['content']}"
            total += len(line)
            if total > max_chars:
                lines.append("...(后续对话省略)")
                break
            lines.append(line)
        return "\n".join(lines)

    # ── 历史任务扫描 ──

    def save_plan_steps(self, stage_progress=None):
        """保存任务状态到 _save_path，可选同步 stage_progress"""
        if not self._save_path:
            raise ValueError("_save_path 为空，无法保存")
        if stage_progress:
            self.update_plan_steps(stage_progress)
        self.save(self._save_path)
    
    @staticmethod
    def list_history_tasks(task_dir: str, status_filter: str = None) -> list[dict]:
        """返回任务列表（扁平结构，供 UI 消费），涵盖所有状态与周期任务。

        Args:
            status_filter: 可选，按状态过滤，如 SubTaskStatus.PENDING.value
        """
        if not os.path.isdir(task_dir):
            return []
        result = []
        for fpath in sorted(glob.glob(os.path.join(task_dir, "task_*_state.json"))):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
            except Exception:
                continue
            s = data.get("subtask", {})
            if not s:
                continue
            pd = data.get("periodic", {})
            is_periodic = bool(pd.get("is_periodic", s.get("is_periodic", False)))
            status = s.get("status", "")
            if status_filter is not None and status != status_filter:
                continue
            result.append({
                "name": s.get(TaskField.SUB_TASK_NAME, "未知任务"),
                "file_name": os.path.basename(fpath),
                "status": status,
                "subtask_status": status,
                "result_judge": s.get("result_judge", ""),
                "result_content": s.get("result_content", ""),
                "messages": s.get("messages", []),
                "file_full_path": fpath,
                "project_path": s.get(TaskField.PROJECT_PATH, ""),
                "task_type": s.get(TaskField.TASK_TYPE, ""),
                "next_execution_time": pd.get("next_execution_time") or s.get("next_execution_time", ""),
                "is_periodic": is_periodic,
                "is_interactive": s.get("is_interactive", False),
                "period": pd.get("period") or s.get("period", ""),
                "sub_task_detail": s.get(TaskField.SUB_TASK_DETAIL, ""),
                "periodic_counter": pd.get("counter", 0),
            })
        return result

    @staticmethod
    def update_pending_task(file_path: str, updates: dict) -> bool:
        """更新计划任务的可编辑字段，通过 load→修改→save 保证数据一致性。"""
        if not file_path or not os.path.exists(file_path):
            return False
        try:
            tm = TaskManager.load(file_path)
            if not tm._subtask:
                return False
            sub = tm._subtask
            sub.sub_task_name = updates.get("task_name", sub.sub_task_name)
            sub.next_execution_time = updates.get("next_execution_time", sub.next_execution_time)
            sub.is_periodic = updates.get("is_periodic", sub.is_periodic)
            sub.period = updates.get("period", sub.period)
            sub.is_interactive = updates.get("is_interactive", sub.is_interactive)
            tm.save(file_path)
            return True
        except (json.JSONDecodeError, IOError):
            return False

    @staticmethod
    def build_history_context(log_dir: str, max_chars: int = 8000) -> str:
        """构建历史任务上下文，供 LLM 判断新任务是否属于历史任务

        仅包含最近 5 个历史任务的摘要和关键对话。
        """
        tasks = [
            t for t in TaskManager.list_history_tasks(log_dir)
            if t['status'] != 'skipped'
        ]
        if not tasks:
            return ""
        lines = ["## 历史任务记录（最近任务）"]
        total = 0
        for ti, t in enumerate(tasks[:15]):
            header = f"\n### 历史任务 {ti+1}: (状态: {t['status']}, 文件: {t['file_name']})"
            total += len(header)
            if total > max_chars:
                lines.append("\n...(更多历史任务省略)")
                break
            lines.append(header)
            icon = {"completed": "●", "failed": "✕", "in_progress": "◉", "pending": "○"} \
                   .get(t["status"], "?")
            sline = (
                f"  {icon} [{t['task_type']}] {t.get('name', '')} - {t.get('sub_task_detail', '')[:100]}"
            )
            if t.get("result_judge"):
                sline += f" → 结果: {t['result_judge']}"
            total += len(sline)
            if total > max_chars:
                break
            lines.append(sline)
            msgs = t.get("messages", [])
            if msgs:
                lines.append(f"  对话 ({len(msgs)} 条):")
                for m in msgs[-3:]:
                    mline = (
                        f"    [{str(m.get('timestamp', ''))[:16]}] "
                        f"{m.get('role','')}: {m.get('content','')[:120]}"
                    )
                    total += len(mline)
                    if total > max_chars:
                        break
                    lines.append(mline)
                if total > max_chars:
                    break
        return "\n".join(lines)


    # ── StageProgress (update_plan) ──

    def create_stage_progress(self, stage_names: list[str]) -> StageProgress:
        """为当前活动子任务创建新的 StageProgress 并写入 plan_steps。"""
        progress = StageProgress(stage_names)
        sub = self._active_subtask()
        if sub:
            sub.plan_steps = progress.to_dict()
        return progress

    def load_stage_progress(self, phase_msgs: list[dict]) -> StageProgress:
        """根据 phase_msgs 初始化 StageProgress，包含阶段名和各阶段步骤。"""
        stage_names = [p["name"] for p in phase_msgs]
        sp = StageProgress(stage_names)
        for p in phase_msgs:
            if p.get("phase_msg"):
                steps = [{"step": s, "status": "pending"} for s in p["phase_msg"]]
                sp.init_stage(p["name"], steps)
        return sp

    def update_plan_steps(self, progress: StageProgress):
        """将 StageProgress 序列化回当前活动子任务的 plan_steps 字段。"""
        sub = self._active_subtask()
        if sub:
            sub.plan_steps = progress.to_dict()

    def _active_subtask(self) -> SubTaskRecord | None:
        return self._subtask


# ================================================================
# 工具函数
# ================================================================

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_execution_time(s: str) -> str:
    """解析执行时间字符串，返回 ISO 格式字符串。

    支持: "now"/"immediate"/"立即" → 当前时间
          "+10m"/"+2h"/"+1d"/"+1w" → 相对时间
          ISO 格式字符串 → 原样返回
    """
    if not s or s.strip().lower() in ("now", "immediate", "立即"):
        return _now_iso()
    s = s.strip()
    if s.startswith("+"):
        return (datetime.now() + _parse_duration(s[1:])).isoformat()
    # 尝试识别 ISO 格式
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                 "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return _now_iso()


def _parse_duration(s: str):
    """解析时长字符串，返回 timedelta。支持: 30m, 2h, 1d, 1w"""
    from datetime import timedelta
    s = s.strip().lower()
    if s.endswith("m"):
        return timedelta(minutes=int(s[:-1]))
    if s.endswith("h"):
        return timedelta(hours=int(s[:-1]))
    if s.endswith("s"):
        return timedelta(seconds=int(s[:-1]))
    if s.endswith("d"):
        return timedelta(days=int(s[:-1]))
    if s.endswith("w"):
        return timedelta(weeks=int(s[:-1]))
    return timedelta(seconds=int(s))

