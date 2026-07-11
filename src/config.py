"""配置管理 —— 基于 dataclass 的类型安全配置"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from llm_client import PROVIDERS

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str = ""
    model: str = "deepseek-v4-pro"
    temperature: float = 0.7
    max_tokens: int = 10240
    memory_enabled: bool = True
    memory_size: int = 40
    llm_max_allowed_rounds: int = 40
    label: str = ""
    active: bool = True


@dataclass
class ExecutionConfig:
    timeout: int = 60
    work_dir: str = "./workspace"
    skills_dir: str = ""
    spc_dir: str = ""
    enable_history_association: bool = True
    task_config_file_path: str = ""
    pending_tasks_file_path: str = ""
    task_dir: str = ""
    inner_space_dir: str = "./inner_space"


@dataclass
class LogConfig:
    dir: str = "./workspace/log"
    log_to_terminal: bool = False
    log_to_file: bool = True
    history: bool = True


@dataclass
class AuthConfig:
    interactive: bool = True
    sensitive_command_check: bool = True


# ── 文本截断长度 ──
TRUNCATION = {
    "log_raw_response":   10000,
    "log_exec_output":     5000,
    "log_llm_interact":    5000,
    "log_llm_prompt":      10000,
    "log_task_cmd":        2300,
    "display_cmd_preview":  120,
    "display_result":       300,
    "history_detail":       8000,
    "evaluate_output":     50000,
    "skill_dir_list":        10,
}


# ── AppConfig ────────────────────────────────────────────────────

@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    llm_list: list = field(default_factory=list)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    log: LogConfig = field(default_factory=LogConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)

    def __post_init__(self):
        """自动初始化：解析 API Key、规范化路径、创建目录"""
        self._init_paths()
        self._init_dirs()
        self._init_api_key()
        # Ensure llm_list has at least the current config
        if not self.llm_list:
            self.llm_list = [asdict(self.llm)]

    def _init_paths(self):
        """将相对路径转为绝对路径（相对于 config.py 所在目录）"""
        import os as _os
        root = str(Path(__file__).parent.parent)
        isd = self.execution.inner_space_dir

        if not self.execution.spc_dir:
            self.execution.spc_dir = isd + "/spc"
        if not self.execution.skills_dir:
            self.execution.skills_dir = isd + "/skills"
        if not self.execution.task_dir:
            self.execution.task_dir = isd + "/task"
        if not self.execution.task_config_file_path:
            self.execution.task_config_file_path = self.execution.spc_dir + "/task_config.json"
        if not self.execution.pending_tasks_file_path:
            self.execution.pending_tasks_file_path = self.execution.task_dir + "/pending_tasks.json"

        self.execution.spc_dir = self._resolve(self.execution.spc_dir, root)
        self.execution.skills_dir = self._resolve(self.execution.skills_dir, root)
        self.execution.task_dir = self._resolve(self.execution.task_dir, root)
        self.execution.task_config_file_path = self._resolve(self.execution.task_config_file_path, root)
        self.execution.pending_tasks_file_path = self._resolve(self.execution.pending_tasks_file_path, root)
        self.log.dir = self._resolve(self.log.dir, root)

    def _init_dirs(self):
        """创建必要的目录"""
        import os as _os
        for d in [self.log.dir, self.execution.task_dir]:
            if d:
                _os.makedirs(d, exist_ok=True)

    def _init_api_key(self):
        """解析 API Key，失败则抛异常"""
        from aes_crypto import is_encrypted, decrypt
        import os as _os
        key = self.llm.api_key
        if not key or not key.strip():
            return
        if is_encrypted(key):
            self.llm.api_key = decrypt(key)
        elif any(key.startswith(p) for p in ("sk-", "fk-", "ak-", "xai-", "hf-")):
            pass  # 原始 key，直接使用
        else:
            resolved = _os.environ.get(key, "")
            if resolved:
                self.llm.api_key = resolved

    @staticmethod
    def _resolve(path: str, root: str) -> str:
        import os as _os
        if not _os.path.isabs(path):
            return _os.path.abspath(_os.path.join(root, path))
        return _os.path.abspath(path)

    # ── 序列化 ──

    def to_dict(self) -> dict:
        d = asdict(self)
        # 向后兼容：保留 memory 段（读取时仍可用）
        d["memory"] = {
            "enabled": self.llm.memory_enabled,
            "size": self.llm.memory_size,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        llm_data = dict(d.get("llm", {}))
        # 向后兼容：旧 config.json 的 memory 段合并到 llm
        if "memory" in d:
            mem = d["memory"]
            llm_data.setdefault("memory_enabled", mem.get("enabled", True))
            llm_data.setdefault("memory_size", mem.get("size", 40))
        return cls(
            llm=LLMConfig(**llm_data),
            execution=ExecutionConfig(**d.get("execution", {})),
            log=LogConfig(**d.get("log", {})),
            auth=AuthConfig(**d.get("auth", {})),
        )

    # ── 加载 / 保存 ──

    @classmethod
    def load(cls, path: str = "") -> "AppConfig":
        """从 JSON 加载配置，合并用户设置后执行 __post_init__"""
        cfg = cls()
        p = Path(path) if path else CONFIG_PATH
        if p.exists():
            user = json.loads(open(p, encoding="utf-8").read())
            cfg._merge(user)
            if "llm_list" in user and user["llm_list"]:
                cfg.llm_list = user["llm_list"]
            else:
                cfg.llm_list = [asdict(cfg.llm)]
            # Ensure one is active AND has a valid key
            has_active = any(e.get("active") and e.get("api_key") for e in cfg.llm_list)
            if not has_active:
                for e in cfg.llm_list:
                    if e.get("api_key"):
                        e["active"] = True
                        break
                else:
                    cfg.llm_list[0]["active"] = True
            # Deactivate entries without key
            for e in cfg.llm_list:
                if not e.get("api_key"):
                    e["active"] = False
            active_entry = next((e for e in cfg.llm_list if e.get("active") and e.get("api_key")), cfg.llm_list[0])
            for k in ("provider", "model", "api_key", "base_url", "temperature", "max_tokens", "memory_enabled", "memory_size", "llm_max_allowed_rounds"):
                if k in active_entry:
                    setattr(cfg.llm, k, active_entry[k])
            cfg.__post_init__()
        return cfg

    def add_llm_entry(self, entry: dict):
        """添加一个新 LLM 配置到列表"""
        entry["active"] = False
        self.llm_list.append(entry)

    def switch_llm(self, index: int):
        """切换到指定索引的 LLM 配置"""
        if 0 <= index < len(self.llm_list):
            for i, e in enumerate(self.llm_list):
                e["active"] = (i == index)
            active = self.llm_list[index]
            for k in ("provider", "model", "api_key", "base_url", "temperature", "max_tokens", "memory_enabled", "memory_size", "llm_max_allowed_rounds"):
                if k in active:
                    setattr(self.llm, k, active[k])
            self._init_api_key()  # re-decrypt

            label = active.get("label") or f"{active.get("provider","")}/{active.get("model","")}"
            print(f"\n🔄 切换模型 → {label}")
    def remove_llm_entry(self, index: int):
        if 0 <= index < len(self.llm_list) and len(self.llm_list) > 1:
            was_active = self.llm_list[index].get("active", False)
            del self.llm_list[index]
            if was_active:
                self.llm_list[0]["active"] = True
                self.switch_llm(0)

    def save(self, path: str = ""):
        """保存到 JSON 文件"""
        p = Path(path) if path else CONFIG_PATH
        d = self.to_dict()
        d["llm_list"] = self.llm_list
        del d["llm"]  # Only use llm_list
        if "memory" in d: del d["memory"]  # Backward compat
        # Re-encrypt keys for safe storage
        from aes_crypto import is_encrypted, encrypt
        for e in d["llm_list"]:
            key = e.get("api_key", "")
            if key and not is_encrypted(key):
                try: e["api_key"] = encrypt(key)
                except: pass
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _merge(self, user: dict):
        """深度合并用户配置到默认值上"""
        for section in ("llm", "execution", "log", "auth"):
            if section in user:
                s = getattr(self, section)
                for k, v in user[section].items():
                    if hasattr(s, k):
                        setattr(s, k, v)

    # ── API Key 解析 ──

    def resolve_api_key(self) -> bool:
        """解析并解密 api_key（AES 加密 / 环境变量 / 原始 key）"""
        from aes_crypto import is_encrypted, decrypt
        api_key = self.llm.api_key
        if not api_key or not api_key.strip():
            return False

        if is_encrypted(api_key):
            try:
                self.llm.api_key = decrypt(api_key)
                return True
            except ValueError:
                return False

        if any(api_key.startswith(p) for p in ("sk-", "fk-", "ak-", "xai-", "hf-")):
            return True

        # 尝试作为环境变量名解析
        resolved = os.environ.get(api_key, "")
        if resolved:
            self.llm.api_key = resolved
            return True
        return False


# ── 兼容旧版 ──

def load_config(path: str = "") -> AppConfig:
    """兼容旧接口：返回 AppConfig 实例。"""
    return AppConfig.load(path)


def save_config(config: AppConfig, path: str = ""):
    config.save(path)


def get_default_config() -> AppConfig:
    return AppConfig()


def list_available_providers() -> list:
    return [{"id": k, "name": v["name"], "models": v["models"], "base_url": v["base_url"]}
            for k, v in PROVIDERS.items()]
