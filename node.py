"""数据模型

定义 Agent 任务执行管线的核心数据结构:
- ActionType: 动作类型枚举 (目前仅支持 shell)
- NodeStatus: 节点执行状态枚举
- TaskNode: 任务节点，封装一次规划的单个执行单元及其结果
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Any


class ActionType(Enum):
    """动作类型枚举

    定义 LLM 规划的任务执行方式。
    当前仅支持 SHELL 类型，预留扩展能力。
    """
    SHELL = "shell"


class NodeStatus(Enum):
    """节点生命周期状态

    PENDING   → 待执行
    EXECUTING → 执行中
    SUCCESS   → 执行成功 (exit_code=0)
    FAILED    → 执行失败
    """
    PENDING    = "pending"
    EXECUTING  = "executing"
    SUCCESS    = "success"
    FAILED     = "failed"


class TaskNode:
    """任务节点

    一次 LLM 规划产生的单个执行单元。

    持有:
    - 原始规划数据 (name, description, actions)
    - 执行状态 (status, result_ok, result_raw)
    - 元数据 (executed_at)

    actions 中的 type 字段决定执行方式，目前仅支持 shell 命令。
    command 属性从 actions['command'] 提取单行可执行命令。
    """
    def __init__(self, data: dict):
        self.name        = data.get("name", "")
        self.description = data.get("description", "")
        
        # actions 原始规划数据（dict，含 type/command 等）
        action          = data.get("actions", {})
        self.actions    = action
        self.action_type = ActionType(action.get("type", "shell"))
        
        # 执行状态与结果
        self.status       = NodeStatus.PENDING
        self.result_raw   = ""          # 原始输出（stdout+stderr）
        self.result_ok    = False       # 执行是否成功（exit_code==0）
        self.executed_at  = 0.0
        
    @property
    def command(self) -> str:
        """从 actions 中提取 shell 命令"""
        return self.actions.get("command", "")
    
    @property
    def is_shell(self) -> bool:
        return self.action_type == ActionType.SHELL
    
    
    def __repr__(self) -> str:
        s = {NodeStatus.PENDING: "⏳", NodeStatus.EXECUTING: "🔄",
             NodeStatus.SUCCESS: "✅", NodeStatus.FAILED: "❌"}.get(self.status, "❓")
        return f"{s} [{self.action_type.value}] {self.name}"
