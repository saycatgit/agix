
"""Flet 模式入口 —— 初始化 Agent / EventQueueManager, 启动 Flet UI"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import flet as ft
from config import AppConfig
from agent import Agent
from auth import AuthHandler
from event_queue_manager import EventQueueManager
from flet_app import build_ui


def main():
    config_path = Path(__file__).parent / "config.json"
    config = AppConfig.load(str(config_path)) if config_path.exists() else AppConfig()
    auth_handler = AuthHandler(
        interactive=config.auth.interactive,
        sensitive_command_check=config.auth.sensitive_command_check,
    )
    eqm = EventQueueManager()
    agent = Agent(config, auth_handler, eqm=eqm)
    agent.is_interactive = True

    print(f"\n🤖 当前模型: {config.llm.provider} / {config.llm.model}")
    print(f"  启动 Flet UI...\n")

    ft.app(target=lambda page: build_ui(page, eqm, agent), view=ft.AppView.FLET_APP_HIDDEN)


if __name__ == "__main__":
    main()
