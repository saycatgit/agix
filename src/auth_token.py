"""Token 本地持久化。"""

import json
import time
from pathlib import Path


class AuthToken:
    """管理认证 token 的本地存储。"""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def save(self, token: str, phone: str = "", expires_at: float = 0) -> None:
        """持久化 token 到本地文件。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"token": token, "phone": phone, "expires_at": expires_at}
        with open(self._path, "w", encoding='utf-8') as f:
            json.dump(data, f)

    def load(self) -> str | None:
        """加载 token，不存在、损坏或已过期返回 None。"""
        if not self._path.exists():
            return None
        try:
            with open(self._path, encoding='utf-8') as f:
                data = json.load(f)
            token = data.get("token")
            expires_at = data.get("expires_at", 0)
            if not token:
                return None
            if expires_at and time.time() > expires_at:
                self.clear()
                return None
            return token
        except (json.JSONDecodeError, KeyError):
            return None

    def clear(self) -> None:
        """清除本地 token（登出）。"""
        if self._path.exists():
            self._path.unlink()
