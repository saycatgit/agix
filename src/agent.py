"""核心 Agent

UI 配置中枢与后台任务调度入口。

职责：
  - 初始化并持有各组件引用（config / llm / chater / executor），供 UI 层访问
  - 启动 Executor 后台工作线程，接管子任务的扫描、执行与周期管理
"""

import glob
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

    # ── 附加信息构建 ──

    def build_attach(self) -> str:
        """构建附加信息：可用技能列表 + SSH连接信息，供 LLM 上下文使用。"""
        parts = ["当前可用外部工具及服务列表（mcp、技能、ssh站点）如下，使用之前先阅读相关md文档（有可用服务时优先使用MCP服务，非必要不创建新skill）"]

        mcp_text = self._scan_mcp_dir()
        if mcp_text:
            parts.append(mcp_text)

        skills_text = self._scan_skills_dir()
        if skills_text:
            parts.append(skills_text)

        ssh_text = self._scan_ssh_config()
        if ssh_text:
            parts.append(ssh_text)

        joined = "\n".join(parts)
        self.logger.log(f"build attach:\n{joined}")
        return "\n\n".join(parts)

    def _scan_skills_dir(self) -> str:
        """扫描 skills_dir 构建技能列表文本。"""
        skills_dir = self.skills_dir
        if not skills_dir or not os.path.isdir(skills_dir):
            return ""

        lines = ["## 可用技能："]
        for skill_dir in sorted(glob.glob(os.path.join(skills_dir, "*"))):
            if not os.path.isdir(skill_dir):
                continue
            name = os.path.basename(skill_dir)
            md = os.path.join(skill_dir, "SKILL.md")
            desc = ""
            if os.path.isfile(md):
                try:
                    with open(md, "r", encoding="utf-8") as f:
                        f.readline()  # 跳过标题行 "# name"
                        for line in f:
                            stripped = line.strip()
                            if stripped:
                                desc = stripped
                                break
                except Exception:
                    pass
            lines.append(f"- **{name}**: {desc or name}")
            lines.append(f"  文档: {md}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def _scan_mcp_dir(self) -> str:
        """提取 mcp.md 中可用服务器表格，详情引导 LLM 自行读取 mcp.md。"""
        mcp_dir = getattr(self.config.paths, "mcp_dir", "")
        if not mcp_dir or not os.path.isdir(mcp_dir):
            return ""

        mcp_md = os.path.join(mcp_dir, "mcp.md")
        if not os.path.isfile(mcp_md):
            return ""

        try:
            with open(mcp_md, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return ""

            # 只提取"可用服务器"部分
            marker = "## MCP可用服务器"
            idx = content.find(marker)
            if idx != -1:
                servers_section = content[idx:].strip()
            else:
                servers_section = ""

            return (
                f"{servers_section}\n\n"
                f"MCP服务的使用方式、注意事项、服务器管理等详情见 `{mcp_md}` 文档。"
            )
        except Exception:
            return ""

    def _scan_ssh_config(self) -> str:
        """提取 ssh.md 中当前SSH表格，详情引导 LLM 自行读取 ssh.md。"""
        ssh_dir = getattr(self.config.paths, "ssh_dir", "")
        if not ssh_dir or not os.path.isdir(ssh_dir):
            return ""

        ssh_md = os.path.join(ssh_dir, "ssh.md")
        if not os.path.isfile(ssh_md):
            return ""

        try:
            with open(ssh_md, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return ""

            # 只提取"当前SSH"部分
            marker = "## 当前SSH"
            idx = content.find(marker)
            if idx != -1:
                ssh_section = content[idx:].strip()
            else:
                ssh_section = ""
            return (
                f"{ssh_section}\n\n"
                f"使用方式、注意事项等详情见 `{ssh_md}` 文档。"
            )
        except Exception:
            return ""
