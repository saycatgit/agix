"""任务状态管理器

维护 Agent 任务管线的完整状态信息：
- 主任务与所有子任务的类型、内容、当前状态
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


class MainTaskStatus(Enum):
    """主任务整体状态"""
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"


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
    is_continuation: bool = False
    related_subtask_task: str = ""
    related_project_path: str = ""
    llm_context_info: str = ""
    extra_prompt:    str = ""
    phase_msgs:     list = field(default_factory=list)
    status:         SubTaskStatus = SubTaskStatus.PENDING
    dir_from:       str = ""
    project_path:   str = ""
    docs_dir:       str = ""
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
        return SubTaskRecord(
            index=index,
            sub_task_detail=item.get(TaskField.SUB_TASK_DETAIL, ""),
            sub_task_name=item.get(TaskField.SUB_TASK_NAME, ""),
            task_type=item.get("task_type", "其他"),
            task_sub_type=item.get("task_sub_type", ""),
            dir_from=item.get("dir_from", ""),
            created_at=_now_iso(),
        )


@dataclass
class MainTaskRecord:
    """主任务记录"""
    main_task_name:   str
    main_task_detail: str = ""
    status:        MainTaskStatus = MainTaskStatus.PENDING
    created_at:    str = ""
    completed_at:  str = ""
    total_rounds:  int = 0


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
        self._main:     MainTaskRecord | None = None
        self._subtasks: list[SubTaskRecord]   = []
        self._global_messages: list[QAMessage] = []
        self._conversation_log: list[dict] = []
        self._save_path = save_path
        self._stage_progress: StageProgress | None = None

    # ── 主任务 ──

    def start(self, main_task_name: str, main_task_detail: str = "") -> MainTaskRecord:
        """开始一个新主任务"""
        self._main = MainTaskRecord(
            main_task_name=main_task_name,
            main_task_detail=main_task_detail,
            status=MainTaskStatus.IN_PROGRESS,
            created_at=_now_iso(),
        )
        self._subtasks.clear()
        self._global_messages.clear()
        self._conversation_log.clear()
        return self._main

    def finish(self, success: bool = True):
        """标记主任务完成"""
        if self._main:
            self._main.status = MainTaskStatus.COMPLETED if success else MainTaskStatus.FAILED
            self._main.completed_at = _now_iso()

    @property
    def main_task(self) -> MainTaskRecord | None:
        """当前主任务记录。"""
        return self._main

    @property
    def status(self) -> MainTaskStatus:
        """主任务整体状态。"""
        return self._main.status if self._main else MainTaskStatus.PENDING

    # ── 子任务管理 ──

    def add_subtask(self, index: int, item: dict) -> SubTaskRecord:
        """从一个 orchestrate 字典项添加子任务记录"""
        rec = SubTaskRecord.from_orchestrate_item(index, item)
        self._subtasks.append(rec)
        return rec

    def add_subtasks_from_orchestrate(self, orchestrate: list[dict]):
        """从完整的 orchestrate 列表批量添加子任务。"""
        """从完整的 orchestrate 列表批量添加子任务"""
        for i, item in enumerate(orchestrate, 1):
            self.add_subtask(i, item)

    def set_subtask_status(self, index: int, status: SubTaskStatus):
        """更新子任务的状态"""
        rec = self._get_sub(index)
        if rec:
            rec.status = status
            if status in (SubTaskStatus.COMPLETED, SubTaskStatus.FAILED, SubTaskStatus.SKIPPED):
                rec.completed_at = _now_iso()

    def set_subtask_project(self, index: int, project_path: str, docs_dir: str):
        """设置子任务的项目路径和文档目录信息。"""
        """设置子任务的项目名称、路径和文档目录"""
        rec = self._get_sub(index)
        if rec:
            rec.project_path = project_path
            rec.docs_dir = docs_dir

    def set_subtask_docs(self, index: int, docs: dict):
        """设置子任务关联的文档路径和名称。"""
        """从 docs 字典提取路径保存（不保存文档内容）"""
        rec = self._get_sub(index)
        if rec:
            paths = []
            for k, v in docs.items():
                if isinstance(v, dict) and v.get("path"):
                    paths.append(v["path"])

    def set_subtask_result(self, index: int, judge: str, content: str, rounds: int = 0):
        """记录子任务的执行结果（成功/失败判定 + 结果摘要 + 消耗轮次）。"""
        """记录子任务执行结果"""
        rec = self._get_sub(index)
        if rec:
            rec.result_judge   = judge
            rec.result_content = content
            rec.round_count    = rounds


    def append_subtasks(self, orchestrate: list[dict], start_index: int | None = None) -> int:
        """向现有子任务列表追加新的子任务。返回第一个新子任务的 index。"""
        """为历史任务延续追加新子任务

        Returns:
            第一个新子任务的 index（即 start_index）
        """
        if start_index is None:
            start_index = len(self._subtasks) + 1
        for j, item in enumerate(orchestrate):
            idx = start_index + j
            self.add_subtask(idx, item)
        return start_index

    def reactivate(self):
        """重新激活任务管理器（重置活跃状态位）。"""
        """将主任务状态重新设为 IN_PROGRESS（用于延续）"""
        if self._main:
            self._main.status = MainTaskStatus.IN_PROGRESS

    def set_subtask_extra(self, index: int, extra: str):
        """设置子任务的额外元信息字段。"""
        """设置子任务附加信息"""
        rec = self._get_sub(index)
        if rec:
            rec.extra = extra

    def set_subtask_extra_prompt(self, index: int, extra_prompt: str):
        """设置子任务配置 extra_prompt。"""
        rec = self._get_sub(index)
        if rec:
            rec.extra_prompt = extra_prompt

    def set_subtask_history_relation(self, index: int, is_continuation: bool,
                                     related_subtask_task: str, related_project_path: str):
        """设置子任务的历史延续关系"""
        rec = self._get_sub(index)
        if rec:
            rec.is_continuation = is_continuation
            rec.related_subtask_task = related_subtask_task
            rec.related_project_path = related_project_path

    def set_subtask_phase_msgs(self, index: int, phase_msgs: list):
        """设置子任务的阶段信息列表"""
        rec = self._get_sub(index)
        if rec:
            rec.phase_msgs = phase_msgs

    def set_subtask_llm_context_info(self, index: int, info: str):
        """设置子任务的 LLM 上下文信息哈希"""
        rec = self._get_sub(index)
        if rec:
            rec.llm_context_info = info

    def get_subtask(self, index: int) -> SubTaskRecord | None:
        """按索引获取子任务记录。"""
        return self._get_sub(index)

    @property
    def subtasks(self) -> list[SubTaskRecord]:
        """所有子任务列表。"""
        return list(self._subtasks)

    @property
    def pending_subtasks(self) -> list[SubTaskRecord]:
        """状态为 PENDING 或 IN_PROGRESS 的子任务。"""
        return [s for s in self._subtasks if s.status == SubTaskStatus.PENDING]

    @property
    def current_subtask(self) -> SubTaskRecord | None:
        """当前正在执行的子任务（首个 IN_PROGRESS）。"""
        """当前正在执行的子任务（第一个 IN_PROGRESS）"""
        for s in self._subtasks:
            if s.status == SubTaskStatus.IN_PROGRESS:
                return s
        return None

    # ── 问答记录 ──

    def add_qa(self, index: int | None, role: str, content: str, context: str = ""):
        """向指定子任务添加一条问答记录。"""
        """记录一条问答消息"""
        msg = QAMessage(role=role, content=content, timestamp=_now_iso(), context=context)
        if index is None:
            self._global_messages.append(msg)
        else:
            rec = self._get_sub(index)
            if rec:
                rec.messages.append(msg)

    def get_qa_history(self, index: int | None = None) -> list[QAMessage]:
        """获取指定子任务（或全局）的问答历史列表。"""
        """获取指定子任务或全局的问答历史"""
        if index is None:
            return list(self._global_messages)
        rec = self._get_sub(index)
        return list(rec.messages) if rec else []

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
                "docs_dir": s.docs_dir, "extra": s.extra,
                "result_judge": s.result_judge, "result_content": s.result_content,
                "round_count": s.round_count,
                "messages": [_msg_to_dict(m) for m in s.messages],
                "created_at": s.created_at, "completed_at": s.completed_at,
                "plan_steps": s.plan_steps,
                "is_continuation": s.is_continuation,
                "related_subtask_task": s.related_subtask_task,
                "related_project_path": s.related_project_path,
                "phase_msgs": s.phase_msgs,
                "llm_context_info": s.llm_context_info,
                "extra_prompt": s.extra_prompt,
            }
            if s.sub_task_name:
                d[TaskField.SUB_TASK_NAME] = s.sub_task_name
            return d

        main = self._main
        return {
            "maintask": {
                TaskField.MAIN_TASK_NAME: main.main_task_name if main else "",
                TaskField.MAIN_TASK_DETAIL: main.main_task_detail if main else "",
                "status": main.status.value if main else MainTaskStatus.PENDING.value,
                "created_at": main.created_at if main else "",
                "completed_at": main.completed_at if main else "",
            },
            "subtasks": [_sub_to_dict(s) for s in self._subtasks],
            "conversation_log": list(self._conversation_log),
            TaskField.GENERAL_MSGS: [_msg_to_dict(m) for m in self._global_messages],
        }

    def save(self, path: str = ""):
        """将状态序列化到 JSON 文件"""
        p = path or self._save_path
        if not p:
            raise ValueError("save() 需要提供 path 参数")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "TaskManager":
        """从 JSON 文件恢复 TaskManager 实例"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tm = cls(save_path=path)

        main_data = data.get("maintask", {})
        if main_data.get(TaskField.MAIN_TASK_NAME):
            tm._main = MainTaskRecord(
                main_task_name=main_data.get(TaskField.MAIN_TASK_NAME, ""),
                main_task_detail=main_data.get(TaskField.MAIN_TASK_DETAIL, ""),
                status=MainTaskStatus(main_data.get("status", "pending")),
                created_at=main_data.get("created_at", ""),
                completed_at=main_data.get("completed_at", ""),
            )

        for sd in data.get("subtasks", []):
            rec = SubTaskRecord(
                index=sd[TaskField.SUBTASK_INDEX],
                sub_task_detail=sd.get(TaskField.SUB_TASK_DETAIL, ""),
                task_type=sd[TaskField.TASK_TYPE],
                sub_task_name=sd.get(TaskField.SUB_TASK_NAME, ""),
                task_sub_type=sd.get(TaskField.TASK_SUB_TYPE, ""),
                dir_from=sd.get("dir_from", ""),
                status=SubTaskStatus(sd.get("status", "pending")),
                                project_path=sd.get("project_path", ""),
                docs_dir=sd.get("docs_dir", ""),
                                extra=sd.get("extra", ""),
                result_judge=sd.get("result_judge", ""),
                result_content=sd.get("result_content", ""),
                round_count=sd.get("round_count", 0),
                messages=[QAMessage(**m) for m in sd.get("messages", [])],
                is_continuation=sd.get("is_continuation", False),
                related_subtask_task=sd.get("related_subtask_task", ""),
                related_project_path=sd.get("related_project_path", ""),
                phase_msgs=sd.get("phase_msgs", []),
                llm_context_info=sd.get("llm_context_info", ""),
                extra_prompt=sd.get("extra_prompt", ""),
                created_at=sd.get("created_at", ""),
                completed_at=sd.get("completed_at", ""),
            )
            rec.plan_steps = sd.get("plan_steps", {})
            tm._subtasks.append(rec)

        tm._conversation_log = data.get("conversation_log", [])
        tm._global_messages = [QAMessage(**m) for m in data.get(TaskField.GENERAL_MSGS, [])]
        return tm

    # ── 汇总查询 ──

    # ── 对话日志 ──

    def add_conversation_entry(self, role: str, content: str,
                               subtask_index: int | None = None):
        """向当前会话的对话日志追加一条记录。"""
        """记录一条对话日志

        role 取值: "user" | "assistant" | "agent"
        subtask_index: 关联的子任务序号，None 表示全局对话
        """
        self._conversation_log.append({
            "role": role,
            "content": content,
            "timestamp": _now_iso(),
            "subtask_index": subtask_index,
        })

    def get_conversation_context(self, max_chars: int = 8000) -> str:
        """截取最近对话内容作为上下文，总量不超过 max_chars。"""
        """格式化为 LLM 可读的对话上下文"""
        if not self._conversation_log:
            return ""
        lines = ["## 当前主任务对话记录"]
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

    def update_task_list(self, task_dir: str):
        """更新 task_list.json 任务索引，保留最近 50 条"""
        try:
            list_path = os.path.join(task_dir, "task_list.json")
            task_list = []
            if os.path.exists(list_path):
                try:
                    with open(list_path, 'r', encoding='utf-8') as f:
                        task_list = json.load(f)
                except Exception:
                    task_list = []

            existing = None
            for i, t in enumerate(task_list):
                if t.get("state_file") == self._save_path:
                    existing = i
                    break

            entry = {
                TaskField.MAIN_TASK_NAME: self.main_task.main_task_name if self.main_task else "",
                TaskField.MAIN_TASK_DETAIL: self.main_task.main_task_detail if self.main_task else "",
                "status": self.main_task.status.value if self.main_task else "",
                "created_at": self.main_task.created_at if self.main_task else "",
                "completed_at": self.main_task.completed_at if self.main_task else "",
                "state_file": self._save_path,
                "subtasks_count": len(self.subtasks),
                "completed_count": sum(1 for s in self.subtasks
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

    @staticmethod
    def scan_history_tasks(log_dir: str) -> list[dict]:
        """扫描日志目录，获取所有已完成/进行中的历史任务摘要"""
        tasks = []
        if not os.path.isdir(log_dir):
            return tasks
        _pat = re.compile(r'task_(\d+)_state\.json$')
        for state_file in glob.glob(os.path.join(log_dir, "task_*_state.json")):
            m = _pat.search(state_file)
            task_num = int(m.group(1)) if m else 0
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue
            main = data.get("maintask", {})
            subtasks = data.get("subtasks", [])
            completed = sum(1 for s in subtasks if s.get("status") == "completed")
            tasks.append({
                "file": state_file,
                "file_name": os.path.basename(state_file),
                "task_num": task_num,
                TaskField.MAIN_TASK_NAME: main.get(TaskField.MAIN_TASK_NAME, ""),
                TaskField.MAIN_TASK_DETAIL: main.get(TaskField.MAIN_TASK_DETAIL, ""),
                "status": main.get("status", ""),
                "created_at": main.get("created_at", ""),
                "completed_at": main.get("completed_at", ""),
                "subtasks_count": len(subtasks),
                "completed_count": completed,
                "subtasks": [{
                    TaskField.SUBTASK_INDEX: s.get(TaskField.SUBTASK_INDEX),
                    TaskField.SUB_TASK_DETAIL: s.get(TaskField.SUB_TASK_DETAIL, ""),
                    TaskField.TASK_TYPE: s.get(TaskField.TASK_TYPE, ""),
                    "status": s.get("status", ""),
                    "result_judge": s.get("result_judge", ""),
                    "result_content": s.get("result_content", ""),
                    "messages": s.get("messages", []),
                } for s in subtasks],
            })
        tasks.sort(key=lambda t: t["task_num"])
        return tasks

    @staticmethod
    def build_history_context(log_dir: str, max_chars: int = 8000) -> str:
        """构建历史任务上下文，供 LLM 判断新任务是否属于历史任务

        仅包含最近 5 个历史任务的摘要和关键对话。
        """
        tasks = TaskManager.scan_history_tasks(log_dir)
        if not tasks:
            return ""
        lines = ["## 历史任务记录（最近任务）"]
        total = 0
        for ti, t in enumerate(tasks[:15]):
            header = (
                f"\n### 历史主任务 {ti+1}: {t[TaskField.MAIN_TASK_DETAIL]}"
                f" (状态: {t['status']}, {t['completed_count']}/{t['subtasks_count']} 完成, 文件: {t['file_name']})"
            )
            total += len(header)
            if total > max_chars:
                lines.append("\n...(更多历史任务省略)")
                break
            lines.append(header)
            # 子任务信息
            for s in t["subtasks"]:
                icon = {"completed": "●", "failed": "✕", "in_progress": "◉", "pending": "○"}\
                       .get(s["status"], "?")
                sline = (
                    f"  子任务{s[TaskField.SUBTASK_INDEX]} {icon} [{s[TaskField.TASK_TYPE]}] {s.get(TaskField.SUB_TASK_DETAIL, '')[:100]}"
                )
                if s.get("result_judge"):
                    sline += f" → 结果: {s['result_judge']}"
                total += len(sline)
                if total > max_chars:
                    break
                lines.append(sline)
            # 子任务的 content 和 messages（替代 conversation_log）
            for s in t["subtasks"]:
                msgs = s.get("messages", [])
                if msgs:
                    lines.append(f"  子任务{s[TaskField.SUBTASK_INDEX]} 对话 ({len(msgs)} 条):")
                    for m in msgs[-3:]:
                        mline = (
                            f"    [{m.get('timestamp','')[:16]}] "
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
        """获取当前 IN_PROGRESS 状态的子任务。"""
        for sub in self._subtasks:
            if sub.status == SubTaskStatus.IN_PROGRESS:
                return sub
        return None


    def _get_sub(self, index: int) -> SubTaskRecord | None:
        """按索引查找子任务记录（内部方法）。"""
        for s in self._subtasks:
            if s.index == index:
                return s
        return None


# ================================================================
# 工具函数
# ================================================================

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
