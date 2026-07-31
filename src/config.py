"""配置管理"""

import json
import os
import requests
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
import sys

# ── LLM 供应商配置 ──
PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "balance_url": "https://api.deepseek.com/user/balance",
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "balance_url": "https://platform.openai.com/usage",
    },
    "moonshot": {
        "name": "月之暗面 Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "balance_url": "https://api.moonshot.cn/v1/users/me/balance",
    },
    "minimax": {
        "name": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        "balance_url": "",
    },
    "stepfun": {
        "name": "阶跃星辰",
        "base_url": "https://api.stepfun.com/v1",
        "balance_url": "",
    },
    "siliconflow": {
        "name": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "balance_url": "https://api.siliconflow.cn/v1/user/info",
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "balance_url": "",
    },
    "qwen": {
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "balance_url": "",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "balance_url": "https://open.bigmodel.cn/api/paas/v4/account/balance",
    },
    "custom": {
        "name": "自定义",
        "base_url": "",
        "balance_url": "",
    },
}


# ── 内部截断常量 ──
MAX_HISTORY_CONTENT = 32768 #262144  # 写入 history 的单个 tool result 最大长度


# 标准用户配置目录
if os.name == 'nt':
    USER_HOME = Path(os.environ.get('APPDATA', str(Path.home()))) / "agix"
else:
    USER_HOME = Path.home() / ".agix"
USER_HOME.mkdir(parents=True, exist_ok=True)


# ── PathConfig: 全部路径由 EFFECTIVE_ROOT 计算，不存入 config.json ──

@dataclass
class PathConfig:
    """所有文件系统路径，基于 EFFECTIVE_ROOT 自动构建。"""
    root: str = ""
    current_work_dir: str = ""  # 运行时工作目录，随任务切换可变，初始值 = config_work_dir
    inner_space_dir: str = ""
    skills_dir: str = ""
    spc_dir: str = ""
    task_dir: str = ""
    config_file_path: str = ""
    token_file: str = ""
    task_config_file_path: str = ""
    log_dir: str = ""
    ssh_dir: str = ""
    ssh_config_path: str = ""
    mcp_dir: str = ""
    mcp_config_path: str = ""
    logo_dir: str = ""

    def __post_init__(self):
        import os as _os
        r = self.root
        self.current_work_dir = r
        isd = _os.path.join(r, "inner_space")
        self.inner_space_dir = isd
        self.spc_dir = _os.path.join(isd, "spc")
        self.skills_dir = _os.path.join(isd, "skills")
        self.task_dir = _os.path.join(isd, "task")
        self.config_file_path = _os.path.join(isd, "config.json")
        self.token_file = _os.path.join(isd, "auth_token.json")
        self.task_config_file_path = _os.path.join(self.task_dir, "task_config.json")
        self.log_dir = _os.path.join(r, "workspace", "log")
        self.ssh_dir = _os.path.join(isd, "ssh")
        self.ssh_config_path = _os.path.join(self.ssh_dir, "ssh.json")
        self.mcp_dir = _os.path.join(isd, "mcp")
        self.mcp_config_path = _os.path.join(isd, "mcp", "mcp.json")
        self.logo_dir = isd


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str = ""
    model: str = "deepseek-v4-pro"
    temperature: float = 0.7
    max_tokens: int = 10240

    organization: str = ""
    project: str = ""
    default_headers: dict = field(default_factory=dict)
    context_window: int = 40
    label: str = ""
    active: bool = True


@dataclass
class ExecutionConfig:
    timeout: int = 60
    enable_history_task_association: bool = True
    max_rounds: int = 40
    memory_enabled: bool = True  # chat 模式持久记忆
    interactive: bool = True
    thinking: bool = True
    config_work_dir: str = ""  # 持久化默认工作目录，空则运行时 os.getcwd() 兜底


@dataclass
class LogConfig:
    enabled: bool = True
    history: bool = True


@dataclass
class AuthConfig:
    sensitive_command_check: bool = True





# ── AppConfig ──

class AppConfig:
    """应用配置聚合 — 路径由 PathConfig 计算，不持久化。"""

    # ── 根目录计算 ──

    @staticmethod
    def _get_root_path() -> Path:
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        else:
            return Path(__file__).parent.parent

    @staticmethod
    def _init_user_home() -> Path:
        """生产环境首次运行时复制资源到 USER_HOME，返回实际根目录。"""
        if not hasattr(sys, "_MEIPASS"):
            return AppConfig._get_root_path()
        user_config = USER_HOME / "inner_space" / "config.json"
        if not user_config.exists():
            import shutil
            USER_HOME.mkdir(parents=True, exist_ok=True)
            current_root = AppConfig._get_root_path().resolve()
            try:
                for dirname in ("workspace", "inner_space"):
                    src, dst = current_root / dirname, USER_HOME / dirname
                    if src.exists() and not dst.exists():
                        shutil.copytree(src, dst)
            except FileNotFoundError as e:
                print(f"[WARN] 生产环境资源复制失败: {e}", file=sys.stderr)
        return USER_HOME

    # ── 初始化 ──

    def __init__(self,
                 llm: LLMConfig | None = None,
                 llm_list: list | None = None,
                 execution: ExecutionConfig | None = None,
                 log: LogConfig | None = None,
                 auth: AuthConfig | None = None):
        self.llm = llm or LLMConfig()
        self.llm_list = llm_list or []
        self.execution = execution or ExecutionConfig()
        self.log = log or LogConfig()
        self.auth = auth or AuthConfig()
        self.sudo_password: str = ""  # 不落盘，仅内存

        # 平台检测
        _sys = sys.platform
        self.system = "windows" if _sys == "win32" else "darwin" if _sys == "darwin" else "linux"

        # 构建路径、创建目录、解析 API Key
        effective_root = str(AppConfig._init_user_home())
        self.paths = PathConfig(root=effective_root)
        self._init_dirs()
        if self.execution.config_work_dir and not os.path.isdir(self.execution.config_work_dir):
            print(f"[ERROR] 配置的工作目录无效，已回退为当前目录: {self.execution.config_work_dir}", file=sys.stderr)
        if not os.path.isdir(self.execution.config_work_dir):
            self.execution.config_work_dir = os.getcwd()
        self.paths.current_work_dir = self.execution.config_work_dir
        self._init_api_key()
        if not self.llm_list:
            self.llm_list = [asdict(self.llm)]
    
    def __getattr__(self, name: str):
        """将未命中属性委托到 self.paths，支持 config.mcp_config_path 等扁平访问。"""
        paths = self.__dict__.get('paths')
        if paths is not None and hasattr(paths, name):
            return getattr(paths, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def _init_dirs(self):
        """创建必要的目录。"""
        import os as _os
        for d in [self.paths.log_dir, self.paths.task_dir]:
            if d:
                _os.makedirs(d, exist_ok=True)

    def _init_api_key(self):
        self.resolve_api_key()

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """序列化为 dict（不含 paths）。"""
        return {
            "execution": asdict(self.execution),
            "log": asdict(self.log),
            "auth": asdict(self.auth),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        llm_data = dict(d.get("llm", {}))
        exec_data = dict(d.get("execution", {}))
        # Backward compat: migrate llm_max_allowed_rounds
        if "max_rounds" not in exec_data and "llm_max_allowed_rounds" in llm_data:
            exec_data["max_rounds"] = llm_data.pop("llm_max_allowed_rounds")
        # Backward compat: migrate memory_enabled
        if "memory_enabled" not in exec_data and "memory_enabled" in llm_data:
            exec_data["memory_enabled"] = llm_data.pop("memory_enabled")
        return cls(
            llm=LLMConfig(**llm_data),
            execution=ExecutionConfig(**exec_data),
            log=LogConfig(**d.get("log", {})),
            auth=AuthConfig(**d.get("auth", {})),
        )

    # ── 加载 / 保存 ──

    @classmethod
    def load(cls) -> "AppConfig":
        """从 JSON 加载配置，合并用户设置。"""
        cfg = cls()
        p = Path(cfg.paths.config_file_path)
        if p.exists():
            user = json.loads(open(p, encoding="utf-8").read())
            cfg._merge(user)
            if cfg.execution.config_work_dir and not os.path.isdir(cfg.execution.config_work_dir):
                print(f"[ERROR] 配置的工作目录无效，已回退为当前目录: {cfg.execution.config_work_dir}", file=sys.stderr)
            if not os.path.isdir(cfg.execution.config_work_dir):
                cfg.execution.config_work_dir = os.getcwd()
            cfg.paths.current_work_dir = cfg.execution.config_work_dir
            if "llm_list" in user and user["llm_list"]:
                cfg.llm_list = user["llm_list"]
            else:
                cfg.llm_list = [asdict(cfg.llm)]
            has_active = any(e.get("active") and e.get("api_key") for e in cfg.llm_list)
            if not has_active:
                for e in cfg.llm_list:
                    if e.get("api_key"):
                        e["active"] = True
                        break
                else:
                    cfg.llm_list[0]["active"] = True
            for e in cfg.llm_list:
                if not e.get("api_key"):
                    e["active"] = False
            active_entry = next((e for e in cfg.llm_list if e.get("active") and e.get("api_key")), cfg.llm_list[0])
            for k in ("provider", "model", "api_key", "base_url", "temperature", "max_tokens", "context_window"):
                if k in active_entry:
                    setattr(cfg.llm, k, active_entry[k])
            if "llm_max_allowed_rounds" in active_entry:
                cfg.execution.max_rounds = active_entry["llm_max_allowed_rounds"]
            if "memory_enabled" in active_entry:
                cfg.execution.memory_enabled = active_entry["memory_enabled"]
            cfg._init_api_key()
        return cfg

    def add_llm_entry(self, entry: dict):
        entry["active"] = False
        self.llm_list.append(entry)

    def switch_llm(self, index: int):
        if 0 <= index < len(self.llm_list):
            for i, e in enumerate(self.llm_list):
                e["active"] = (i == index)
            active = self.llm_list[index]
            for k in ("provider", "model", "api_key", "base_url", "temperature", "max_tokens", "context_window"):
                if k in active:
                    setattr(self.llm, k, active[k])
            if "llm_max_allowed_rounds" in active:
                self.execution.max_rounds = active["llm_max_allowed_rounds"]
            if "memory_enabled" in active:
                self.execution.memory_enabled = active["memory_enabled"]
            self._init_api_key()
            label = active.get("label") or f"{active.get('provider','')}/{active.get('model','')}"
            print(f"\n切换模型 -> {label}")

    def remove_llm_entry(self, index: int):
        if 0 <= index < len(self.llm_list) and len(self.llm_list) > 1:
            was_active = self.llm_list[index].get("active", False)
            del self.llm_list[index]
            if was_active:
                self.llm_list[0]["active"] = True
                self.switch_llm(0)

    def save(self):
        """保存到 JSON 文件（不含路径字段）。"""
        p = Path(self.paths.config_file_path)
        print(f"保存配置到 {p}")
        d = self.to_dict()
        d["llm_list"] = self.llm_list
        d.pop("llm", None)
        from utils import Utils
        for e in d["llm_list"]:
            key = e.get("api_key", "")
            if key and not Utils.is_encrypted(key):
                try:
                    e["api_key"] = Utils.encrypt(key)
                except Exception:
                    pass
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _merge(self, user: dict):
        """深度合并用户配置到默认值上。"""
        for section in ("llm", "execution", "log", "auth"):
            if section in user:
                s = getattr(self, section)
                for k, v in user[section].items():
                    if hasattr(s, k):
                        setattr(s, k, v)

    def resolve_api_key(self) -> bool:
        """解析并解密 api_key。"""
        from utils import Utils
        api_key = self.llm.api_key
        if not api_key or not api_key.strip():
            return False
        if Utils.is_encrypted(api_key):
            try:
                self.llm.api_key = Utils.decrypt(api_key)
                return True
            except ValueError:
                return False
        if any(api_key.startswith(p) for p in ("sk-", "fk-", "ak-", "xai-", "hf-")):
            return True
        resolved = os.environ.get(api_key, "")
        if resolved:
            self.llm.api_key = resolved
            return True
        return False


# ── 模型列表获取 ──

def fetch_models_by_provider(provider: str, api_key: str) -> list[str]:
    """根据供应商名获取模型名称列表。仅 DeepSeek 支持，其他返回空列表。"""
    if provider != "deepseek":
        return []
    try:
        resp = requests.get("https://api.deepseek.com/models",
                            headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return sorted([m["id"] for m in data.get("data", []) if m.get("id")], key=lambda x: x.lower())
    except Exception:
        return []
