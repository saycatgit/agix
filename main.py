#!/usr/bin/env python3
"""DeepSeek 风格 Agent —— 交互式 CLI 入口"""

import sys, os, json
from pathlib import Path
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import WordCompleter, Completer

# 将当前目录加入模块搜索路径（便于导入本地模块）
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config, save_config, get_default_config, list_available_providers
from agent import Agent
from llm_client import LLMClient
from task_manager import TaskManager
from auth import AuthHandler
import aes_crypto  # AES 磁盘序列号加密


# ============================================================================
# 辅助函数
# ============================================================================




def _resolve_api_key(config: dict) -> bool:
    """
    解析 api_key 配置项。支持两种格式:
      1. 加密存储: 'enc:aes:<base64>' → 磁盘序列号解密
      2. 原始 key: 以 sk-、fk-、ak- 等开头 → 直接使用（兼容旧版）
    返回 True 表示解析成功，False 表示未找到有效 key。
    """
    llm = config.get("llm")
    if not llm:
        return False

    api_key = llm.get("api_key", "")
    if not api_key.strip():
        return False

    # 格式1: AES 加密存储
    if aes_crypto.is_encrypted(api_key):
        try:
            decrypted = aes_crypto.decrypt(api_key)
            config["llm"]["api_key"] = decrypted
            return True
        except ValueError as e:
            print(f"  ⚠ 密钥解密失败: {e}")
            return False

    # 格式2: 直接是原始 key（兼容旧版未加密的配置）
    if any(api_key.startswith(p) for p in ("sk-", "fk-", "ak-", "xai-", "hf-")):
        return True

    # 无法识别的格式
    return False





def setup_wizard() -> dict:
    """首次配置向导：选择 LLM 供应商并设置 API Key。
    Key 使用磁盘序列号 AES 加密后存入 config.json，不写入 shell rc 文件。
    """
    print("\n🔧 首次配置向导\n")

    providers = list_available_providers()
    print("可用的 LLM 供应商:")
    for i, p in enumerate(providers, 1):
        print(f"  {i}. {p['name']} ({p['id']}) — 模型: {', '.join(p['models'][:3])}")

    choice = input(f"\n选择供应商 [1-{len(providers)}，默认1]: ").strip()
    idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(providers) else 0
    provider = providers[idx]

    api_key = ""
    while not api_key:
        api_key = input(f"请输入 {provider['name']} API Key: ").strip()
        if not api_key:
            print("  API Key 不能为空，请重新输入")

    models = provider["models"]
    if models:
        print(f"可用模型: {', '.join(models)}")
        model = input(f"选择模型 [默认 {models[0]}]: ").strip() or models[0]
    else:
        model = input("输入模型名称: ").strip()

    # 以现有 config.json 为基础，只覆盖向导中重新指定的 LLM 字段
    try:
        config = load_config()
    except Exception:
        config = get_default_config()
    config["llm"]["provider"] = provider["id"]
    # 使用磁盘序列号加密存储 API Key（不写入 shell rc 文件）
    encrypted_key = aes_crypto.encrypt(api_key)
    config["llm"]["api_key"] = encrypted_key
    config["llm"]["base_url"] = provider["base_url"]
    config["llm"]["model"] = model

    save_config(config)
    print(f"\n✅ 配置已保存到 config.json\n")
    return config


def initialize_agent(config_path: Path):
    """
    加载配置、解析 API Key、创建并返回 Agent 实例和配置字典。
    若配置不存在或解析失败，则进入配置向导。
    """
    if not config_path.exists():
        config = setup_wizard()
    else:
        config = load_config()

    while not _resolve_api_key(config):
        print("\n⚙ 需要配置 LLM API Key，进入配置向导...\n")
        config = setup_wizard()

    auth_handler = AuthHandler(
        interactive=config.get("auth", {}).get("interactive", True),
        sensitive_command_check=config.get("auth", {}).get("sensitive_command_check", True)
    )
    agent = Agent(config, auth_handler)
    return agent, config


# ============================================================================
# 命令处理
# ============================================================================

def _handle_command(cmd: str, config: dict, agent: Agent):
    """
    处理以 '/' 开头的命令。
    返回值：
      - False：表示退出程序
      - Agent 实例：表示需要替换当前 agent（例如重新配置后）
      - None：表示继续使用当前 agent
    """
    parts = cmd.split()
    c = parts[0].lower()

    if c == "/exit":
        agent.logger.log("👋 再见！", always=True)
        return False

    elif c == "/help":
        print("""
┌─────────────────────────────────────────────────────────┐
│  可用命令                                                 │
├─────────────────────────────────────────────────────────┤
│  /help          显示此帮助信息                             │
│  /exit          退出程序                                  │
│  /llm           重新配置 LLM 模型和 API Key                │
│  /config        查看当前配置                               │
│  /history       查看历史任务                               │
│  /clear         清屏                                      │
├─────────────────────────────────────────────────────────┤
│  多行输入: Esc+Enter 发送，Enter 换行                      │
│  直接输入任务描述即可交给 Agent 执行                        │
└─────────────────────────────────────────────────────────┘
""")
        return None

    elif c == "/llm":
        print("\n⚙ 重新配置 LLM...\n")
        new_cfg = setup_wizard()
        config.clear()
        config.update(new_cfg)
        # 重新创建 AuthHandler 和 Agent
        auth_handler = AuthHandler(
            interactive=config.get("auth", {}).get("interactive", True),
            sensitive_command_check=config.get("auth", {}).get("sensitive_command_check", True)
        )
        new_agent = Agent(config, auth_handler)
        return new_agent  # 返回新 agent，调用方会更新

    elif c == "/config":
        safe = {k: v for k, v in config.get("llm", {}).items() if k != "api_key"}
        safe["api_key"] = "***" if config.get("llm", {}).get("api_key") else "(未设置)"
        print(f"\n当前 LLM 配置:\n{json.dumps(safe, indent=2, ensure_ascii=False)}")
        return None

    elif c == "/history":
        wd = config.get("execution", {}).get("work_dir", "./workspace")
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), wd, "log")
        history_ctx = TaskManager.build_history_context(log_dir)
        if history_ctx:
            print(f"\n{history_ctx}")
        else:
            print("\n(无历史任务记录)")
        return None

    elif c == "/clear":
        print("\033[2J\033[H", end="")
        return None

    else:
        print(f"\n未知命令: {c}，输入 /help 查看可用命令")
        return None


class SlashCommandCompleter(Completer):
    """只有输入以 / 开头时才触发命令补全，避免输入中间位置 / 时误弹出菜单"""

    def __init__(self, words, meta_dict=None):
        self._word_completer = WordCompleter(words, meta_dict=meta_dict)

    def get_completions(self, document, complete_event):
        text = document.text.strip()
        if not text.startswith('/'):
            return
        yield from self._word_completer.get_completions(document, complete_event)


# ============================================================================
# 运行模式
# ============================================================================

def interactive_mode():
    """交互式循环：读取用户目标 → 执行 → 输出结果。"""
    config_path = Path(__file__).parent / "config.json"
    agent, config = initialize_agent(config_path)

    # 显示当前模型信息
    llm_info = config.get("llm", {})
    providers = {p["id"]: p for p in list_available_providers()}
    provider_name = providers.get(llm_info.get("provider", ""), {}).get("name", "未知")
    print(f"\n🤖 当前模型: {provider_name} / {llm_info.get('model', '未知')}")

    # 命令补全器
    completer = SlashCommandCompleter(
        ['/help', '/exit', '/llm', '/config', '/history', '/clear'],
        meta_dict={
            '/help':    '显示帮助信息',
            '/exit':    '退出程序',
            '/llm':     '重新配置 LLM 模型和 API Key',
            '/config':  '查看当前 LLM 配置',
            '/history': '查看历史任务记录',
            '/clear':   '清屏',
        },
    )

    print("\n💡 输入 / 查看命令  |  Enter 发送  |  Ctrl+C 退出\n")

    while True:
        try:
            raw = pt_prompt("🎯 ", completer=completer,
                            complete_while_typing=True,
                            reserve_space_for_menu=6).strip()
        except (EOFError, KeyboardInterrupt):
            agent.logger.log("\n👋 再见！", always=True)
            break

        if not raw:
            continue

        # 长文本预览
        if len(raw) > 120:
            preview = raw[:80].replace('\n', ' ') + "..."
            print(f"  📋 ({len(raw)} 字符) {preview}")

        # 处理命令
        if raw.startswith("/"):
            result = _handle_command(raw, config, agent)
            if result is False:
                break
            elif isinstance(result, Agent):
                agent = result  # 更新 agent
            continue

        # 正常任务执行
        try:
            result = agent.run(raw, mode="chat")
        except Exception as e:
            agent.logger.log(f"\n❌ 执行出错: {e}", always=True)
            import traceback
            traceback.print_exc()
            continue


def single_run(goal: str):
    """命令行单次执行模式：python main.py <任务描述>。"""
    config_path = Path(__file__).parent / "config.json"
    agent, config = initialize_agent(config_path)

    print(f"\n🤖 执行任务: {goal}\n")
    try:
        result = agent.run(goal, mode="chat")
        # 直接输出结果
        print("\n📋 结果:")
        print(result.get('content', '(无内容)'))
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()


def main():
    if len(sys.argv) > 1:
        single_run(" ".join(sys.argv[1:]))
    else:
        interactive_mode()


if __name__ == "__main__":
    main()