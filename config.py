"""配置管理

负责 JSON 配置文件的读写、默认值合并、供应商查询。
核心数据结构:
  - DEFAULT_CONFIG: 默认配置字典 (llm/execution/log/memory/docs/auth)
  - TRUNCATION: 文本截断长度统一管理常量
"""

import json
import os
from pathlib import Path
from llm_client import PROVIDERS

DEFAULT_CONFIG = {
    "llm": {
        "provider": "deepseek",
        "api_key": "",
        "base_url": "",
        "model": "deepseek-v4-pro",
        "temperature": 0.7,
        "max_tokens": 10240,
    },
    "execution": {
        "timeout": 60,              # shell 命令超时秒数
        "llm_rounds": 40,           # 重规划最大轮次（防止无限循环）
        "work_dir": "./workspace",   # 临时文件工作目录
        "skills_dir": "./workspace/skills",      # 技能目录
        "spc_dir": "./spc",                         # spec文档目录
        "enable_history_association":True  #启用历史task项目记录关联记忆
    },
    "log": {
        "dir": "./workspace/log",                              # 日志目录，为空则使用 {work_dir}/log
        "log_to_terminal": False,           # 是否打印过程信息到终端
        "log_to_file": True,        # 是否写入日志文件
        "history": True,            # 是否将 LLM 对话历史保存到独立日志
    },
    "memory": {
        "enabled": True,            # 是否启用 LLM 会话记忆
        "size": 40,                 # 保留最近 N 轮对话，尽量和最大轮次一致
    },
    
    "auth": {
        "interactive": True,               # 是否交互式确认（False 则自动拒绝）
        "sensitive_command_check": True,   # 是否检查敏感命令
    },
}

# ── 文本截断长度统一管理 ──
TRUNCATION = {
    # ── 日志文件输出截断（仅影响日志，不影响 LLM prompt）──
    "log_raw_response":   10000,    # 规划/评估 LLM 原始响应存入日志的最大长度
    "log_exec_output":     5000,    # 单个任务执行输出存入日志的最大长度
    "log_llm_interact":    5000,    # executor/planner 内部 LLM 交互记录响应的最大长度
    "log_llm_prompt":       10000,    # executor/planner 内部 LLM 交互 system/user 的最大长度
    "log_task_cmd":       2300,    # 重规划任务命令日志最大长度

    # ── 终端显示截断（仅影响打印，不影响日志）──
    "display_cmd_preview":  120,    # 终端命令预览最大长度
    "display_result":       300,    # 终端单个任务结果最大长度

    # ── LLM Prompt/记忆截断（控制 token 消耗）──
    "history_detail":       8000,    # 写入 LLM 会话记忆的单个结果最大长度
    "evaluate_output":     50000,    # 评估时发送给 LLM 的汇总结果最大长度
    "skill_dir_list":        10,    # 技能目录列表错误提示中显示的最大条目数
}
CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config(path: str = "") -> dict:
    """加载 JSON 配置文件

    Args:
        path: 配置文件路径，默认 CONFIG_PATH (config.json)

    Returns:
        与 DEFAULT_CONFIG 深度合并后的完整配置 dict。
        用户配置中的字段会覆盖默认值，未设置的字段保持默认。
    """
    p = Path(path) if path else CONFIG_PATH
    user = json.loads(open(p, encoding="utf-8").read()) if p.exists() else {}
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    _deep_merge(cfg, user)
    return cfg


def save_config(config: dict, path: str = ""):
    """保存配置到 JSON 文件

    Args:
        config: 配置字典
        path: 目标路径，默认 CONFIG_PATH
    """
    p = Path(path) if path else CONFIG_PATH
    with open(p, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_default_config() -> dict:
    """返回 DEFAULT_CONFIG 的深拷贝

    Returns:
        不从文件读取的默认配置字典
    """
    return json.loads(json.dumps(DEFAULT_CONFIG))


def list_available_providers() -> list:
    """列出所有可用的 LLM 供应商

    Returns:
        [{"id": str, "name": str, "models": list, "base_url": str}, ...]
    """
    return [{"id": k, "name": v["name"], "models": v["models"], "base_url": v["base_url"]}
            for k, v in PROVIDERS.items()]


def _deep_merge(base: dict, override: dict):
    """深度合并两个字典，override 覆盖 base

    递归处理嵌套字典，非字典值直接覆盖。
    """
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
