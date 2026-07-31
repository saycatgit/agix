"""事件队列管理器 —— 管理 4 个队列 + 2 个同步事件

四个队列:
  chat_display_queue  — chat 线程 -> UI 线程 (display / ask 消息)
  task_display_queue  — task 线程 -> UI 线程 (display / ask 消息)
  to_chat_queue       — UI 线程 -> chat 线程 (user_input / response 消息)
  to_task_queue       — UI 线程 -> task 线程 (user_input / response 消息)

两个事件:
  chat_ask — 标记 chat 线程正在阻塞等待用户回答
  task_ask — 标记 task 线程正在阻塞等待用户回答

消息格式 (JSON):
  {MsgField.CONTENT: str, MsgField.TYPE: MsgType,
   MsgField.ID: str}   # ID 仅 ask / response 类型必填
"""

import queue
import threading
import time
import uuid
from enum import Enum
from utils import Utils

from meta import MsgType, MsgField, MsgStyle

class EventQueueManager:
    """统一管理所有队列及同步事件"""

    def __init__(self, config=None):
        self.chat_display_queue = queue.Queue()
        self.task_display_queue = queue.Queue()
        self.to_chat_queue = queue.Queue()
        self.to_task_queue = queue.Queue()

        self.chat_ask = threading.Event()
        self.task_ask = threading.Event()
        self.chat_ask.set()   # 初始: 不在等待
        self.task_ask.set()

        self._chat_pending_ask_id: str = ""
        self._task_pending_ask_id: str = ""
        # 配置引用，用于读取默认 timeout
        self._config = config

    # ---------- 消息构造 ----------

    @staticmethod
    def make_msg(content: str, msg_type, msg_id: str = "",
                 style: MsgStyle | None = None) -> dict:
        msg = {MsgField.CONTENT: content, MsgField.TYPE: msg_type}
        if style is not None:
            msg[MsgField.STYLE] = style
        msg[MsgField.ID] = msg_id or str(uuid.uuid4())
        return msg

    # ---------- display 消息 ----------

    def send_display(self, content: str, *, mode: str = "chat",
                     style: MsgStyle | None = None,
                     msg_type: MsgType | None = None):
        """工作线程 -> UI 线程: 发送展示内容"""
        actual_style = style or MsgStyle.ASSISTANT
        msg = self.make_msg(content, msg_type or MsgType.DISPLAY, style=actual_style)
        if mode == "chat":
            self.chat_display_queue.put(msg)
        else:
            self.task_display_queue.put(msg)

    def send_debug(self, content: str, *, mode: str = "chat"):
        """工作线程 -> UI: 发送 debug 信息，样式比普通 display 更显眼"""
        msg = self.make_msg(content, MsgType.DEBUG, style=MsgStyle.DEBUG)
        if mode == "chat":
            self.chat_display_queue.put(msg)
        else:
            self.task_display_queue.put(msg)

    def send_thinking(self, content: str, *, mode: str = "chat"):
        """工作线程 -> UI: 发送思维链/项目进度信息，非阻塞，不等待用户响应"""
        msg = self.make_msg(content, MsgType.THINKING, style=MsgStyle.THINKING)
        if mode == "chat":
            self.chat_display_queue.put(msg)
        else:
            self.task_display_queue.put(msg)

    def send_error(self, content: str, *, mode: str = "chat"):
        """工作线程 -> UI: 发送错误信息，红色错误样式展示"""
        msg = self.make_msg(content, MsgType.DISPLAY, style=MsgStyle.ERROR)
        if mode == "chat":
            self.chat_display_queue.put(msg)
        else:
            self.task_display_queue.put(msg)

    # ---------- user_input 消息 ----------

    def send_user_input(self, content: str, *, mode: str = "chat"):
        """各种需求 -> chater 线程: 发送消息给 chater 处理"""
        msg = self.make_msg(content, MsgType.USER_INPUT)
        if mode == "chat":
            self.to_chat_queue.put(msg)
        else:
            self.to_task_queue.put(msg)

    # ---------- ask / response 流程 ----------

    def ask_user(self, question: str, *, mode: str = "chat",
                 timeout: float = None) -> str:
        """工作线程调用: 向 UI 发提问并阻塞等待用户回答。"""
        Utils.play_notification()
        msg_id = str(uuid.uuid4())
        msg = self.make_msg(question, MsgType.ASK, msg_id, style=MsgStyle.ASK)
        return self._wait_for_response(msg, msg_id, mode, timeout)

    def ask_for_password(self, question: str = "请输入密码", *, mode: str = "chat",
                         timeout: float = None) -> str:
        """弹出密码输入框，阻塞等待用户输入。"""
        msg_id = str(uuid.uuid4())
        msg = self.make_msg(question, MsgType.ASK_FOR_PASSWORD, msg_id)
        return self._wait_for_response(msg, msg_id, mode, timeout)

    def ask_for_confirmation(self, question: str, *, mode: str = "chat",
                             timeout: float = None) -> str:
        """弹出确认按钮（是/否），阻塞等待用户选择。默认返回\"否\"。"""
        msg_id = str(uuid.uuid4())
        msg = self.make_msg(question, MsgType.ASK_FOR_CONFIRMATION, msg_id)
        return self._wait_for_response(msg, msg_id, mode, timeout)

    def ask_for_auth_confirmation(self, question: str, *, mode: str = "chat",
                                  timeout: float = None) -> str:
        """弹出敏感命令确认弹窗（允许/本次会话允许/拒绝/本次会话拒绝）。默认返回\"deny\"。"""
        msg_id = str(uuid.uuid4())
        msg = self.make_msg(question, MsgType.ASK_FOR_AUTH_CONFIRMATION, msg_id)
        return self._wait_for_response(msg, msg_id, mode, timeout)

    def _wait_for_response(self, msg: dict, msg_id: str, mode: str,
                           timeout: float = None) -> str:
        """内部: 发送 ask 消息并阻塞等待响应。"""
        if timeout is None:
            timeout = (self._config.execution.timeout
                       if self._config else 60.0)
        if mode == "chat":
            self._chat_pending_ask_id = msg_id
            target_q = self.chat_display_queue
            resp_q = self.to_chat_queue
        else:
            self._task_pending_ask_id = msg_id
            target_q = self.task_display_queue
            resp_q = self.to_task_queue

        ask_event = self.chat_ask if mode == "chat" else self.task_ask

        target_q.put(msg)
        ask_event.clear()

        start = time.monotonic()
        try:
            while True:
                if timeout is not None:
                    elapsed = time.monotonic() - start
                    if elapsed >= timeout:
                        return ""
                    remain = max(timeout - elapsed, 0.1)
                else:
                    remain = 1.0
                try:
                    response = resp_q.get(timeout=remain)
                    if (response.get(MsgField.TYPE) == MsgType.USER_INPUT and
                            response.get(MsgField.ID) == msg_id):
                        return response.get(MsgField.CONTENT, "")
                    resp_q.put(response)
                except queue.Empty:
                    continue
        finally:
            if mode == "chat":
                self._chat_pending_ask_id = ""
            else:
                self._task_pending_ask_id = ""
            ask_event.set()

    def respond_to_ask(self, content: str, *, msg_id: str, mode: str = "chat"):
        """UI 线程调用: 回复某个 ask 消息"""
        msg = self.make_msg(content, MsgType.USER_INPUT, msg_id)
        if mode == "chat":
            self.to_chat_queue.put(msg)
        else:
            self.to_task_queue.put(msg)

    # ---------- 状态查询 ----------

    def is_asking(self, mode: str = "chat") -> bool:
        if mode == "chat":
            return not self.chat_ask.is_set()
        return not self.task_ask.is_set()

    def get_pending_ask_id(self, mode: str = "chat") -> str:
        if mode == "chat":
            return self._chat_pending_ask_id
        return self._task_pending_ask_id

    # ---------- 便捷取出 ----------

    def drain_display(self, mode: str = "chat") -> list:
        """非阻塞取出显示队列中所有消息"""
        q = self.chat_display_queue if mode == "chat" else self.task_display_queue
        items = []
        while True:
            try:
                items.append(q.get_nowait())
            except queue.Empty:
                break
        return items

    # ── 控制消息 ──

    def send_control(self, action: str, mode: str = "chat"):
        """UI 线程调用：发送控制消息（stop/end）到 worker 队列"""

        msg = self.make_msg(action, MsgType.CONTROL)
        if mode == "chat":
            self.to_chat_queue.put(msg)
        else:
            self.to_task_queue.put(msg)
