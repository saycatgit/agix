from enum import Enum
import uuid

class MsgType(str, Enum):
    USER_INPUT = "user_input"
    DISPLAY = "display"
    ASK = "ask"
    RESPONSE = "response"
    STATUS = "status"
    TASK_NAME = "task_name"
    ACTION = "action"
    THINKING = "thinking"


class MsgField:
    CONTENT = "content"
    TYPE = "message_type"
    ID = "message_id"
    STYLE = "style"


class MsgStyle:
    USER = "user"
    ASSISTANT = "assistant"
    ASK = "ask"
    ERROR = "error"
    WARN = "warn"
    STATUS = "status"
    TASK_NAME = "task_name"
    ACTION = "action"
    THINKING = "thinking"



"""共享元数据：TaskField 常量 + 工具方法"""


class TaskField:
    """total_results 字典的 key 常量"""
    JUDGE = "judge"
    SUB_TASK = "sub_task"
    TASK_TYPE = "task_type"
    SUB_TYPE = "sub_type"
    SUBTASK_INDEX = "subtask_index"
    PROJECT_PATH = "project_path"
    CONTENT = "content"
    COST = "cost"
    LOG_PATH = "log_path"
    TASK_STATE = "task_state"

    @staticmethod
    def RET_JSON_FALSE(content: str) -> dict:
        return {TaskField.JUDGE: "false", TaskField.CONTENT: content}

    @staticmethod
    def RET_JSON_TRUE(content: str) -> dict:
        return {TaskField.JUDGE: "true", TaskField.CONTENT: content}
    
    @staticmethod
    def IS_FALSE(ret: dict) -> bool:
        return ret.get(TaskField.JUDGE, "") == "false"