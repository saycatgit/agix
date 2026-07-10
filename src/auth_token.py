"""Token 本地持久化 —— 存储到 ~/.agix/auth_token.json，支持过期检查"""

import json
import time
from pathlib import Path

TOKEN_DIR = Path.home() / ".agix"
TOKEN_FILE = TOKEN_DIR / "auth_token.json"


def save_token(token: str, phone: str = "", expires_at: float = 0) -> None:
    """持久化 token 到本地文件。"""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    data = {"token": token, "phone": phone, "expires_at": expires_at}
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)


def load_token() -> str | None:
    """从本地文件加载 token。

    不存在、损坏或已过期都返回 None。
    """
    if not TOKEN_FILE.exists():
        return None
    try:
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        token = data.get("token")
        expires_at = data.get("expires_at", 0)
        if not token:
            return None
        # 本地过期判断（服务端也会校验，这里提前过滤避免无效请求）
        if expires_at and time.time() > expires_at:
            clear_token()
            return None
        return token
    except (json.JSONDecodeError, KeyError):
        return None


def clear_token() -> None:
    """清除本地 token（登出）。"""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
