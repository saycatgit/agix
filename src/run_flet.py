"""Flet 模式入口 —— 初始化 Agent / EventQueueManager, 启动 Flet UI"""

import json
import os
import platform
import sys
import urllib.request
from pathlib import Path
import subprocess
import flet as ft
from config import AppConfig
from agent import Agent
from auth import AuthHandler
from event_queue_manager import EventQueueManager
import flet_desktop
from flet_app import build_ui, build_login_view
from auth_token import AuthToken

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
    config = AppConfig.load()
    auth_handler = AuthHandler(
        interactive=config.execution.interactive,
        sensitive_command_check=config.auth.sensitive_command_check,
    )
    eqm = EventQueueManager(config=config)
    agent = Agent(config, auth_handler, eqm=eqm)

    server_url = os.environ.get("AGIX_AUTH_SERVER", "http://8.130.188.188")

    print(f"\n🤖 当前模型: {config.llm.provider} / {config.llm.model}")
    print(f"   认证服务: {server_url}")

    # 检查本地缓存的 token
    auth_token = AuthToken(config.paths.token_file)
    saved_token = auth_token.load()
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
            auth_token.clear()

    def on_login(token: str, expires_at: float = 0):
        print(f"\n✓ 登录成功 (token: {token[:8]}...)")
        auth_token.save(token, expires_at=expires_at)
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

CORE_PACKAGES = ["flet", "openai", "cryptography", "requests", "paramiko"]
# 关键包的精确版本要求（版本不匹配则强制重装，确保与阿里云客户端二进制对齐）
REQUIRED_VERSIONS = {"flet": "0.85.3"}
PRIVATE_REPO = "http://www.agix.cc/deps/packages"


def _ensure_dependencies():
    """启动前检查核心依赖，缺失时优先从自托管源安装，不可达则回退 PyPI。"""
    # PyInstaller 打包后依赖已内置，跳过检查
    if getattr(sys, 'frozen', False):
        return

    missing = []
    for pkg in CORE_PACKAGES:
        try:
            mod = __import__(pkg)
        except ImportError:
            missing.append(pkg)
            continue
        # 版本检查：仅针对 REQUIRED_VERSIONS 中的包
        if pkg in REQUIRED_VERSIONS:
            required_ver = REQUIRED_VERSIONS[pkg]
            actual_ver = getattr(mod, "__version__", None)
            if actual_ver is None:
                from importlib.metadata import version as pkg_version
                actual_ver = pkg_version(pkg)
            if actual_ver != required_ver:
                missing.append(f"{pkg}=={required_ver}")

    if not missing:
        return

    system = AppConfig().system
    plat_map = {"linux": "linux_x86_64", "windows": "win_amd64", "darwin": "macosx_arm64"}
    plat_dir = plat_map.get(system)
    if not plat_dir:
        print(f"⚠ 未知平台 {system}，跳过依赖安装")
        return

    print(f"\n📦 检测到缺失依赖: {', '.join(missing)}")
    pip_args = [sys.executable, "-m", "pip", "install", "--quiet"]

    # 优先从自托管源安装
    find_url = f"{PRIVATE_REPO}/{plat_dir}/"
    try:
        print(f"   尝试从 {find_url} 安装...")
        subprocess.check_call(
            pip_args + ["--find-links", find_url, "--trusted-host", "www.agix.cc"] + missing,
            timeout=120,
        )
        print("   ✓ 依赖安装完成")
        return
    except Exception as e:
        print(f"   ✗ 自托管源不可达: {e}")
        print(f"   回退 PyPI 安装...")

    # 回退 PyPI
    try:
        subprocess.check_call(pip_args + missing, timeout=120)
        print("   ✓ 依赖安装完成")
    except Exception as e:
        print(f"   ✗ PyPI 安装失败: {e}")
        print("   请手动执行: pip install openai cryptography requests paramiko")
        sys.exit(1)


def _get_flet_artifact_name() -> str:
    """返回当前平台的 Flet 客户端归档文件名。"""
    try:
        from flet_desktop import get_artifact_filename
        return get_artifact_filename()
    except Exception:
        # 兜底：按 flet 官方命名规则 fallback
        system = AppConfig().system
        if system == "windows":
            return "flet-windows.zip"
        if system == "darwin":
            return "flet-macos.tar.gz"
        # Linux fallback: 使用 flet 官方 arch 映射
        machine = platform.machine()
        arch_map = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
        arch = arch_map.get(machine, machine)
        distro_override = os.environ.get("FLET_LINUX_DISTRO", "ubuntu24.04")
        return f"flet-linux-{distro_override}-light-{arch}.tar.gz"


if __name__ == "__main__":
    _ensure_dependencies()

    # 设置 Flet 客户端二进制自托管下载源
    os.environ["FLET_CLIENT_URL"] = f"http://www.agix.cc/deps/flet/v{flet_desktop.version.version}/{_get_flet_artifact_name()}"
    print(f"   Flet 客户端: {os.environ['FLET_CLIENT_URL']}")

    ft.run(main, view=ft.AppView.FLET_APP_HIDDEN)
