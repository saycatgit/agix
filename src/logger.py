"""统一日志模块 —— 所有模块共用此 Logger 实例写日志"""

import os
import threading
from datetime import datetime
from pathlib import Path


class Logger:
    """日志管理器

    维护两个输出通道:
      - 文件输出 (path): 写入 run_*.log 文件
      - 终端输出: 仅在 log_to_terminal=True 时打印
      - 管道输出: 通过 eqm 发送到 UI
    """
    _thread_mode = threading.local()

    @classmethod
    def mark_thread(cls, mode: str):
        """标记当前线程为 chat 或 task 模式"""
        cls._thread_mode.value = mode

    def __init__(self, log_config=None, eqm=None):
        self.path = ""
        self.eqm = eqm
        if log_config is not None:
            self.enabled = log_config.log_to_file
            self.log_to_terminal = log_config.log_to_terminal
            self._log_dir = log_config.dir
        else:
            self.enabled = True
            self.log_to_terminal = True
            self._log_dir = ""
        if self._log_dir:
            self.open_log()

    def open_log(self):
        """创建日志文件，返回路径"""
        os.makedirs(self._log_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.path = os.path.join(self._log_dir, f"run_{ts}.log")
        self.write(f"Agent 执行日志 | {datetime.now()}\n")
        return self.path

    def write(self, msg: str):
        """写入日志文件 (不打印到终端)

        Args:
            msg: 要写入的内容
        """
        """写入日志，目录不存在时自动重建"""
        if not self.enabled or not self.path:
            return
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(msg + '\n')
        except FileNotFoundError:
            log_dir = os.path.dirname(self.path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(msg + '\n')

    def writeln(self, *lines):
        """写入多行"""
        for line in lines:
            self.write(line)

    @staticmethod
    def _clean_ansi(text: str) -> str:
        import re
        return re.sub(r'\x1b\[[0-9;]*m', '', text)

    def log(self, msg: str, always: bool = False):
        """写日志 + 终端输出 + 管道推送"""
        self.write(msg)
        if self.log_to_terminal or always:
            print(msg)
        if self.eqm and always:
            clean = self._clean_ansi(msg).strip()
            if clean:
                mode = getattr(self._thread_mode, "value", "chat")
                self.eqm.send_display(clean, mode=mode)
