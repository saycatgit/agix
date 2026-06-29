"""统一日志模块 —— 所有模块共用此 Logger 实例写日志"""

import os
from datetime import datetime
from pathlib import Path


class Logger:
    """日志管理器

    维护两个输出通道:
      - 文件输出 (path): 写入 run_*.log 文件
      - 终端输出: 仅在 log_to_terminal=True 时打印
    """
    def __init__(self):
        self.path = ""
        self.enabled = True
        self.log_to_terminal = True

    def init(self, log_dir: str):
        """创建日志目录和文件，返回日志路径"""
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.path = os.path.join(log_dir, f"run_{ts}.log")
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

    def log(self, msg: str, always: bool = False):
        """记录一条日志

        Args:
            msg: 日志内容
            always: True 时始终打印到终端，否则仅在 log_to_terminal 模式打印
        """
        """写日志 + 终端输出（统一入口）"""
        self.write(msg)
        if self.log_to_terminal or always:
            print(msg)
