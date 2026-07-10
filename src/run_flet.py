"""Flet 模式入口 —— 初始化 Agent / EventQueueManager, 启动 Flet UI"""

import json
import os
import sys
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import flet as ft
from config import AppConfig
from agent import Agent
from auth import AuthHandler
from event_queue_manager import EventQueueManager
from flet_app import build_ui, build_login_view
from auth_token import load_token, save_token, clear_token


def _verify_token(server_url: str, token: str) -> bool:
    """向认证服务器验证 token 是否有效。"""
    try:
        req = urllib.request.Request(
            f"{server_url}/api/verify_token",
            data=json.dumps({"token": token}).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return data.get("valid", False)
    except Exception:
        return False


def main(page: ft.Page):
    """Flet 桌面应用入口 —— 先检查本地 token，有效则跳过登录。"""
    config_path = Path(__file__).parent.parent / "config.json"
    config = AppConfig.load(str(config_path)) if config_path.exists() else AppConfig()
    auth_handler = AuthHandler(
        interactive=config.auth.interactive,
        sensitive_command_check=config.auth.sensitive_command_check,
    )
    eqm = EventQueueManager()
    agent = Agent(config, auth_handler, eqm=eqm)
    agent.is_interactive = True

    server_url = os.environ.get("AGIX_AUTH_SERVER", "http://8.130.188.188")

    print(f"\n🤖 当前模型: {config.llm.provider} / {config.llm.model}")
    print(f"   认证服务: {server_url}")

    # 检查本地缓存的 token
    saved_token = load_token()
    if saved_token:
        print("   检查本地 token...")
        if _verify_token(server_url, saved_token):
            print("   ✓ token 有效，跳过登录")
            print("  启动 Flet UI...\n")
            build_ui(page, eqm, agent)
            page.window.visible = True
            page.update()
            return
        else:
            print("   ✗ token 无效，需要重新登录")
            clear_token()

    def on_login(token: str, expires_at: float = 0):
        print(f"\n✓ 登录成功 (token: {token[:8]}...)")
        save_token(token, expires_at=expires_at)
        page.clean()
        page.window.width = 900
        page.window.height = 600
        build_ui(page, eqm, agent)
        page.update()
        # 将窗口推到前台
        page.window.always_on_top = True
        page.window.always_on_top = False
        page.window.focused = True

    print("  启动 Flet UI...\n")
    build_login_view(page, on_login, server_url)


if __name__ == "__main__":
    ft.run(main, view=ft.AppView.FLET_APP_HIDDEN)
