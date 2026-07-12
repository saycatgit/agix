"""统一日志模块 —— 按线程模式分文件写入"""

import os
import threading
from datetime import datetime


class Logger:
    """日志管理器 —— 根据线程模式写入 chat_*.log 或 task_*.log"""
    _thread_local = threading.local()

    def __init__(self, log_config=None, log_dir=None):
        self.path = ""
        self.enabled = log_config.enabled if log_config is not None else True
        self._log_dir = log_dir if log_dir is not None else ""
        if self._log_dir:
            os.makedirs(self._log_dir, exist_ok=True)
        Logger._log_dir = self._log_dir

    @classmethod
    def mark_thread(cls, mode: str):
        """标记当前线程为 chat 或 task 模式，并为其绑定专属日志文件"""
        cls._thread_local.mode = mode
        ts = datetime.now().strftime('%Y%m%d')
        logfile = f"{mode}_{ts}.log"
        log_dir = getattr(cls, '_log_dir', '')
        if log_dir:
            cls._thread_local.logpath = os.path.join(log_dir, logfile)

    def write(self, msg: str):
        """写入日志文件，优先使用当前线程绑定的 logpath"""
        logpath = getattr(self._thread_local, 'logpath', None) or self.path
        if not logpath:
            return
        try:
            with open(logpath, 'a', encoding='utf-8') as f:
                f.write(msg + '\n')
        except FileNotFoundError:
            log_dir = os.path.dirname(logpath)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            with open(logpath, 'a', encoding='utf-8') as f:
                f.write(msg + '\n')

    def log(self, msg: str):
        """写日志"""
        if not self.enabled:
            return
        self.write(msg)
