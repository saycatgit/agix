"""核心 Agent

UI 配置中枢与后台任务调度入口。

职责：
  - 初始化并持有各组件引用（config / llm / chater / executor），供 UI 层访问
  - 启动 Executor 后台工作线程，接管子任务的扫描、执行与周期管理
"""

import os

from llm_client import LLMClient
from logger import Logger
from executor import Executor
from chater import Chater


class Agent:
    """Agent 配置中枢

    职责：初始化核心组件、启动 Executor 后台调度。
    任务执行全链路已由 Executor._worker 接管。
    """

    def __init__(self, config, auth_handler=None, eqm=None):
        self.config = config
        self.eqm = eqm
        self.auth = auth_handler


        self.logger = Logger(config.log, log_dir=config.paths.log_dir)
        Logger.mark_thread("main")

        self.skills_dir = config.paths.skills_dir
        self.chater = Chater(agent=self, config=self.config, logger=self.logger, eqm=self.eqm)
        self.executor = Executor(self, self.config.paths.task_dir, eqm=self.eqm)

        if self.eqm:
            self.executor.start()
