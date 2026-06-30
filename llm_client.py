"""LLM 客户端 —— 统一 OpenAI 兼容接口

支持功能：
  - 6 种 LLM 供应商（DeepSeek/Qwen/OpenAI/GLM/Moonshot/自定义）
  - 会话记忆（可配置轮数）
  - JSON 模式输出（chat_json）
  - LLM 交互计数（call_count）
  - 系统环境信息收集与注入（get_system_info / prepend_system_info）
"""

from typing import Optional
from openai import OpenAI
import re , os, time,locale, platform,json 
from typing import Optional, List, Dict, Any

from openai import BadRequestError

PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-v4-pro", "deepseek-v4-flash"],
    },
    "qwen": {
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.7-max", "qwen3.7-plus"],
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-5", "glm-5.1", "glm-5.2"],
    },
    "moonshot": {
        "name": "Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    "custom": {
        "name": "自定义",
        "base_url": "",
        "models": [],
    },
}

class LLMClient:

    def __init__(self, config: dict, logger=None):
        provider = config.get("provider", "deepseek")
        provider_info = PROVIDERS.get(provider, PROVIDERS["custom"])

        api_key = config.get("api_key", "")
        # 如果 api_key 不是以 sk-/fk-/ak- 等常见 key 前缀开头，视为环境变量名
        if api_key and not any(api_key.startswith(p) for p in ("sk-", "fk-", "ak-", "SECRET:")):
            api_key = os.environ.get(api_key, api_key)
        base_url = config.get("base_url") or provider_info["base_url"]
        self.model = config.get("model", provider_info["models"][0] if provider_info["models"] else "")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 10240)

        if not api_key:
            print(f"\n❌ 未配置 {provider_info['name']} 的 API Key")
            print(f"   请设置环境变量后重试，或删除 config.json 重新运行配置向导\n")
            raise SystemExit(1)

        valid_models = provider_info.get("models", [])
        if valid_models and self.model not in valid_models:
            msg = f"警告: 模型 '{self.model}' 不在已知列表 {valid_models} 中\n   如果 API 返回 400 错误，请检查 config.json 中的 model 字段"
            if logger:
                logger.log(msg, always=True)
            else:
                print(f"警告: 模型 '{self.model}' 不在已知列表 {valid_models} 中")
                print(f"   如果 API 返回 400 错误，请检查 config.json 中的 model 字段")

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.provider_name = provider_info["name"]

        # 会话记忆
        self.history: list[dict] = []
        self.last_raw_response: str = ""
        self.memory_enabled = config.get("memory_enabled", True)
        self.memory_size = config.get("memory_size", 20)  # 最多保留 20 轮对话
        self.call_count = 0  # LLM 交互次数统计
        self.history_log_path = ""  # 历史日志路径

    # ---- 核心聊天 ----

    def chat(self, prompt: str, user_message: str,
             json_mode: bool = False, use_memory: Optional[bool] = None) -> str:

        messages = [{"role": "system", "content": prompt}]

        if self.memory_enabled and self.history:
            start = max(0, len(self.history) - (self.memory_size * 2))
            start = self._snap_to_valid_start(start)
            messages.extend(self.history[start:])

        messages.append({"role": "user", "content": user_message})

        # 规范化 tool_calls 中的 function.arguments 为 JSON 字符串
        # 阿里云 API 严格要求此字段必须是 JSON 字符串，不能是 dict
        for m in messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments")
                    if args is not None and not isinstance(args, str):
                        fn["arguments"] = json.dumps(args, ensure_ascii=False)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        _supports_json_object = self.model not in (
            "deepseek-v4-pro", "deepseek-v4-flash",
            "deepseek-chat", "deepseek-reasoner",
        )
        if json_mode and _supports_json_object:
            kwargs["response_format"] = {"type": "json_object"}

        max_retries = 3
        for attempt in range(max_retries):
            response = self.client.chat.completions.create(**kwargs)
            content_ = response.choices[0].message.content or ""
            if content_.strip():
                break
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s 退避
        content = content_
        self.last_raw_response = content
        self.call_count += 1

        if self.memory_enabled:
            self.history.append({"role": "user", "content": user_message})
            self.history.append({"role": "assistant", "content": content})
        # 写入独立历史日志
        if self.history_log_path:
            try:
                self._write_history_log(
                    f"\n{'='*60}\n[{self.call_count}] SYSTEM:\n{prompt[:5000]}\n\n"
                    f"[{self.call_count}] USER:\n{user_message[:5000]}\n\n"
                    f"[{self.call_count}] ASSISTANT:\n{content[:5000]}\n")
            except Exception:
                pass

        return content

    def chat_json(self, prompt: str, user_message: str,
                  use_memory: Optional[bool] = None) -> dict:
        raw = self.chat(prompt, user_message, json_mode=True, use_memory=use_memory)
        raw = raw.strip().lstrip("\ufeff")  # strip BOM
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw, "parse_error": True}


    def chat_with_tools(self, prompt: str, user_message: str,
                        tools: list[dict],
                        use_memory: Optional[bool] = None) -> dict:
        """带 function calling 的对话。

        tools 示例:
        [{
            "type": "function",
            "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气",
            "parameters": {
                "type": "object",
                "properties": {
                "city": {"type": "string", "description": "城市名"}
                },
                "required": ["city"]
            }
            }
        }]

        Returns:
        {"type": "text", "content": "..."} 或
        {"type": "tool_calls", "calls": [{"id":..., "name":..., "args":...}]}
        若解析失败，返回 {"type": "error", "message": "..."}
        """
        messages = [{"role": "system", "content": prompt}]

        if self.memory_enabled and self.history:
            start = max(0, len(self.history) - (self.memory_size * 2))
            start = self._snap_to_valid_start(start)
            messages.extend(self.history[start:])

        messages.append({"role": "user", "content": user_message})

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools": tools,
            "tool_choice": "auto",
        }

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            self._write_history_log(f"❌ API调用失败: {e}\n")
            return {"type": "error", "message": f"LLM API错误: {e}"}

        msg = response.choices[0].message
        self.call_count += 1

        # 记录用户消息
        if self.history_log_path:
            self._write_history_log(
                f"\n{'='*60}\n[{self.call_count}] TOOLS USER:\n{user_message[:2000]}\n"
            )

        # ---------- 处理工具调用 ----------
        if msg.tool_calls:
            calls = []
            parse_failed = False

            for tc in msg.tool_calls:
                try:
                    args = self.safe_parse_arguments(tc.function.arguments)
                except ValueError as e:
                    # 解析失败，记录详细日志
                    error_msg = f"工具 '{tc.function.name}' 参数解析失败: {e}"
                    if self.history_log_path:
                        self._write_history_log(
                            f"❌ {error_msg}\n"
                            f"原始参数: {tc.function.arguments}\n"
                        )
                    # 可以选择继续（用空字典）或直接返回错误
                    # 这里我们标记失败并跳过该调用，或抛出自定义异常让上层重试
                    # 为了稳健，我们返回错误信息，由上层决定是否重试
                    parse_failed = True
                    # 如果希望继续，可设置 args = {} 并记录错误
                    # 但这里我们直接返回错误类型，表示本次调用失败
                    return {
                        "type": "error",
                        "message": f"工具参数解析失败: {tc.function.name} - {tc.function.arguments[:200]}"
                    }

                calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": args,
                })

            # 记录工具调用日志
            if self.history_log_path:
                try:
                    lines = [f"[{self.call_count}] TOOLS CALL\n"]
                    for c in calls:
                        lines.append(f"  → {c['name']}[{c['id']}]({json.dumps(c['args'], ensure_ascii=False)})\n")
                    self._write_history_log(''.join(lines))
                except Exception:
                    pass

            # 更新历史（包括工具调用消息）
            if self.memory_enabled:
                self.history.append({"role": "user", "content": user_message})
                # 保存 assistant 消息，但截断超大 function.arguments 的 content 字段
                # 阿里云 API 对回放历史中过长的 arguments 有严格限制
                msg_dict = msg.model_dump()
                MAX_ARG_SIZE = 32768  # 32KB，只截断真正超大的工具参数
                for tc in msg_dict.get("tool_calls", []):
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "")
                    if isinstance(args, str) and len(args) > MAX_ARG_SIZE:
                        try:
                            parsed = json.loads(args)
                            if isinstance(parsed, dict) and "content" in parsed:
                                parsed["content"] = (
                                    f"[超大内容已省略，见工具执行结果。"
                                    f"文件: {parsed.get('path', '?')}, "
                                    f"原 {len(parsed['content'])} 字符]")
                                fn["arguments"] = json.dumps(parsed, ensure_ascii=False)
                        except (json.JSONDecodeError, TypeError):
                            pass  # 非法的 JSON 参数保持原样
                self.history.append(msg_dict)

            return {"type": "tool_calls", "calls": calls}

        # ---------- 普通文本回复 ----------
        content = msg.content or ""
        self.last_raw_response = content
        if self.history_log_path:
            try:
                self._write_history_log(
                    f"[{self.call_count}] TOOLS ASSISTANT:\n{content[:20000]}\n"
                )
            except Exception:
                pass

        if self.memory_enabled:
            self.history.append({"role": "user", "content": user_message})
            self.history.append({"role": "assistant", "content": content})

        return {"type": "text", "content": content}

    def _write_history_log(self, content: str):
        """写入历史日志，自动创建目录"""
        if not self.history_log_path:
            return

        os.makedirs(os.path.dirname(self.history_log_path), exist_ok=True)
        with open(self.history_log_path, 'a', encoding='utf-8') as hf:
            hf.write(content)

    def _snap_to_valid_start(self, start: int) -> int:
        """Ensure the history slice doesn't start with orphaned tool messages.

        An orphaned tool message is one whose preceding assistant message
        (with tool_calls) was trimmed off. The OpenAI/DeepSeek API rejects
        messages where a 'tool' role appears without a prior assistant
        message containing tool_calls.

        We scan forward from `start` and skip any leading tool messages
        until we hit a non-tool message, which guarantees valid grouping.
        """
        if start >= len(self.history):
            return start
        i = start
        while i < len(self.history) and self.history[i].get("role") == "tool":
            i += 1
        return i


    def dump_history(self, filepath: str = ""):
        """导出当前历史记录到文件，方便调试。

        Args:
            filepath: 输出路径，默认 <log_dir>/history_dump_<timestamp>.json
        """
        import json
        if not filepath:
            import time
            ts = time.strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.dirname(self.history_log_path) if self.history_log_path else "."
            filepath = os.path.join(log_dir, f"history_dump_{ts}.json")
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
        return filepath

    def submit_tool_result(self, tool_call_id: str, result: str):
        """将函数执行结果追加到 hisry，供 LLM 下一轮使用"""
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        })
        if self.history_log_path:
            try:
                self._write_history_log(
                    f"  TOOL RESULT[{tool_call_id}] :\n{result[:2000]}\n")
            except Exception:
                pass

    # ---- 记忆管理 ----

    # ---- 供应商查询 ----

    @classmethod
    def list_providers(cls) -> dict:
        return PROVIDERS

    # ---- 系统信息 ----

    @staticmethod
    def get_system_info() -> str:
        """收集当前运行环境信息，作为会话上下文发给 LLM

        Args:
            work_dir: 工作目录路to径，如果不传则使用 os.getcwd()
        """

        try:
            encoding = locale.getpreferredencoding()
            lang = os.environ.get("LANG", "not set")
        except Exception:
            encoding = "unknown"
            lang = "not set"

        parts = [
            f"操作系统: {platform.platform()}",
            f"内核版本: {platform.release()}",
            f"架构: {platform.machine()}",
            f"Python 版本: {platform.python_version()}",
            f"Shell: {os.environ.get('SHELL', 'unknown')}",
            f"当前用户: {os.environ.get('USER', 'unknown')}",
            f"主机名: {platform.node()}",
            f"语言环境: LANG={lang}",
            f"编码: {encoding}"
        ]
        return "\n".join(parts)

    def prepend_system_info(self):
        """将系统信息插入到会话历史最前面

        Args:
            work_dir: 工作目录路径，传给 get_system_info
        """
        info = self.get_system_info()
        # 如果 history 为空或第一条不是系统信息，则插入
        if not self.history or self.history[0].get("content", "") != f"[系统环境]\n{info}":
            self.history.insert(0, {"role": "user", "content": f"[系统环境]\n{info}"})
            self.history.insert(1, {
                "role": "assistant",
                "content": "已了解系统环境信息。"
            })
    

    def safe_parse_arguments(self, raw_args: str) -> Dict[str, Any]:
        """
        尝试多种策略解析 LLM 返回的参数字符串，返回字典。
        若解析失败，抛出明确异常（包含原始内容）。
        """
        if not raw_args:
            return {}

        # 策略1：直接解析
        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            pass

        # 策略2：提取 JSON 对象或数组（去除多余说明文字）
        match = re.search(r'(\{.*\}|\[.*\])', raw_args, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 策略3：修复常见问题（未转义控制字符、尾逗号）
        cleaned = raw_args.replace(chr(10), r'\n').replace(chr(13), r'\r').replace(chr(9), r'\t')
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 策略4：处理截断的 JSON（max_tokens 不够时常见）
        stripped = raw_args.rstrip()
        if not stripped.endswith('"}') and not stripped.endswith(']'):
            try:
                fixed = stripped + '"}'
                result = json.loads(fixed.replace(chr(10), r'\n').replace(chr(13), r'\r').replace(chr(9), r'\t'))
                return result
            except json.JSONDecodeError:
                pass

        # 抛出异常，带详细诊断信息
        detail = raw_args[:500]
        if len(raw_args) > 500:
            detail += f"\n...（共 {len(raw_args)} 字符，最后100字符：{raw_args[-100:]}）"
        hint = ""
        if not raw_args.rstrip().endswith('"}') and not raw_args.rstrip().endswith(']'):
            hint = " [JSON 可能被 max_tokens 截断，尝试增大 config.json 中的 llm.max_tokens]"
        raise ValueError(f"无法解析工具参数，原始内容：\n{detail}{hint}")
