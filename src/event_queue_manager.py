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
  {"content": str, "message_type": "display"|"ask"|"response"|"user_input",
   "message_id": str}   # message_id 仅 ask / response 类型必填
"""

import queue
import threading
import uuid


class EventQueueManager:
    """统一管理所有队列及同步事件"""

    def __init__(self):
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

    # ---------- 消息构造 ----------

    @staticmethod
    def make_msg(content: str, msg_type: str, msg_id: str = "",
                 style: str = "") -> dict:
        msg = {"content": content, "message_type": msg_type}
        if style:
            msg["style"] = style
        if msg_type in ("ask", "response"):
            msg["message_id"] = msg_id or str(uuid.uuid4())
        return msg

    # ---------- display 消息 ----------

    def send_display(self, content: str, *, mode: str = "chat",
                     style: str = ""):
        """工作线程 -> UI 线程: 发送展示内容"""
        msg = self.make_msg(content, "display", style=style)
        if mode == "chat":
            self.chat_display_queue.put(msg)
        else:
            self.task_display_queue.put(msg)

    # ---------- user_input 消息 ----------

    def send_user_input(self, content: str, *, mode: str = "chat"):
        """UI 线程 -> 工作线程: 发送用户输入"""
        msg = self.make_msg(content, "user_input")
        if mode == "chat":
            self.to_chat_queue.put(msg)
        else:
            self.to_task_queue.put(msg)

    # ---------- ask / response 流程 ----------

    def ask_user(self, question: str, *, mode: str = "chat",
                 timeout: float = None) -> str:
        """工作线程调用: 向 UI 发提问并阻塞等待用户回答。"""
        msg_id = str(uuid.uuid4())
        msg = self.make_msg(question, "ask", msg_id)

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

        try:
            while True:
                try:
                    response = resp_q.get(timeout=timeout or 1.0)
                    if (response.get("message_type") == "response" and
                            response.get("message_id") == msg_id):
                        return response.get("content", "")
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
        msg = self.make_msg(content, "response", msg_id)
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
