"""LLM 客户端 —— 统一 OpenAI 兼容接口

支持功能：
  - 6 种 LLM 供应商（DeepSeek/Qwen/OpenAI/GLM/Moonshot/自定义）
  - 会话记忆（可配置轮数）
  - JSON 模式输出（chat_json）
  - LLM 交互计数（call_count）
  - 系统环境信息收集与注入（get_system_info / prepend_system_info）
"""

from typing import Optional
from config import PROVIDERS, MAX_HISTORY_CONTENT

from openai import OpenAI
import re , os, sys, time,locale, platform,json 
from typing import Optional, List, Dict, Any
from prompts import history_context_summary_prompt
from openai import BadRequestError


# ── 历史压缩提示词 ──
HISTORY_CONTEXT_SUMMARY_PROMPT = """请对以下对话历史进行总结提炼，保留以下关键信息：
- 用户的核心需求、目标和偏好
- 已完成的主要操作和结果
- 重要的文件路径、代码位置和项目结构
- 未解决的问题和待办事项
- 关键的技术决策和约束条件
- 任何对后续对话有帮助的上下文信息

请用简洁的中文总结，保留所有关键事实但省略冗余的中间过程和重复内容。
不要使用"用户"等第三人称指代，直接以第一视角陈述。"""

class LLMClient:

    def __init__(self, config, logger=None, log_history=False, memory_file=None):
        # 支持 LLMConfig 或 dict
        if hasattr(config, "provider"):
            # LLMConfig
            provider = config.provider
            api_key = config.api_key
            base_url = config.base_url
            model = config.model
            temperature = config.temperature
            max_tokens = config.max_tokens
            context_window = config.context_window
        else:
            # dict (兼容)
            provider = config.get("provider", "deepseek")
            api_key = config.get("api_key", "")
            base_url = config.get("base_url", "")
            model = config.get("model", "")
            temperature = config.get("temperature", 0.7)
            max_tokens = config.get("max_tokens", 10240)
            context_window = config.get("context_window", 20)

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        provider_info = PROVIDERS[provider]
        if not api_key:
            print(f"\n❌ 未配置 {provider_info['name']} 的 API Key")
            print(f"   请设置环境变量后重试，或删除 config.json 重新运行配置向导\n")
            print("（可在设置中配置密钥后重试）")

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.provider = provider
        self._api_key = api_key
        self.provider_name = provider_info["name"]

        # 会话记忆
        self.history: list[dict] = []
        self.last_raw_response: str = ""
        self.context_window = context_window
        self.memory_file = memory_file
        self._last_saved_count = 0
        self.history_compress_summary: str = ""
        if self.memory_file:
            self._load_memory()
            self._last_saved_count = len(self.history)
        self.call_count = 0  # LLM 交互次数统计
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
        self._balance_before = None  # 任务前余额快照
        self.logger = logger
        self.log_history = log_history
        self.last_system_prompt = ""  # 最近一次系统提示词

    # ---- 核心聊天 ----

    def _query_balance(self) -> dict | None:
        """查询当前账户余额，返回原始数据；失败返回 None。"""
        import requests as req
        provider = getattr(self, "provider", "deepseek")
        provider_info = PROVIDERS.get(provider, {})
        balance_url = provider_info.get("balance_url", "")
        api_key = getattr(self, "_api_key", "")

        if not balance_url:
            return None

        try:
            resp = req.get(
                balance_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            return resp.json()
        except Exception:
            return None

    def _parse_balance(self, data: dict) -> float | None:
        """从余额 API 返回中提取总余额（元），兼容 DeepSeek/Zhipu 格式。"""
        if not data:
            return None
        # DeepSeek 格式
        if data.get("is_available"):
            infos = data.get("balance_infos", [])
            total = 0.0
            for info in infos:
                try:
                    total += float(info.get("total_balance", 0))
                except (ValueError, TypeError):
                    pass
            return total if infos else None
        # Zhipu 格式（假设返回 {"data": {"balance": ...}}）
        if "data" in data:
            try:
                return float(data["data"].get("balance", 0))
            except (ValueError, TypeError, AttributeError):
                pass
        return None
    def init_task_counters(self):
        """新任务开始时初始化：清零计数器 + 记录余额快照。"""
        self.call_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
        data = self._query_balance()
        self._balance_before = self._parse_balance(data)
    def get_cost_from_balance(self) -> str:
        """查询当前余额并与快照对比，返回费用字符串。"""
        if self._balance_before is None:
            return ""
        data = self._query_balance()
        after = self._parse_balance(data)
        if after is None:
            return ""
        delta = self._balance_before - after
        if delta >= 0:
            return f" | 账户余额差值 ¥{delta:.4f} (¥{self._balance_before:.2f} → ¥{after:.2f}) (同一Key可能有其他应用消耗)"
        else:
            return f" | 账户余额增加 ¥{abs(delta):.4f}"

    def check_balance(self):
        """查询并打印当前 LLM 账户余额（/balance 命令调用）。"""
        data = self._query_balance()
        if data is None:
            provider = getattr(self, "provider", "deepseek")
            print(f"  供应商 {provider} 未配置余额查询接口或查询失败。请登录官网控制台查看。")
            return
        total = self._parse_balance(data)
        if total is not None:
            print(f"  余额: ¥{total:.2f}")
        else:
            print(f"  余额查询结果: {data}")

    MODEL_PRICES = {
        # (prompt_price_per_M, completion_price_per_M) in RMB
        "deepseek-v4-pro":       (2, 8),
        "deepseek-v4-flash":     (2, 8),
        "qwen3.7-max":           (3, 12),
        "qwen3.7-plus":          (1.5, 6),
        "gpt-4o":                (17, 68),
        "gpt-4o-mini":           (1, 4),
        "gpt-3.5-turbo":         (0.5, 1.5),
        "glm-5":                 (1, 1),
        "glm-5.1":               (1, 1),
        "glm-5.2":               (1, 1),
        "moonshot-v1-8k":        (12, 12),
        "moonshot-v1-32k":       (24, 24),
        "moonshot-v1-128k":      (60, 60),
    }

    def _track_usage(self, usage):
        """从 API 返回的 usage 对象中累加 token 和费用。"""
        if not usage:
            return
        p = usage.prompt_tokens or 0
        c = usage.completion_tokens or 0
        self.total_prompt_tokens += p
        self.total_completion_tokens += c
        price = self.MODEL_PRICES.get(self.model)
        if price:
            cost = (p / 1_000_000) * price[0] + (c / 1_000_000) * price[1]
            self.total_cost += cost

    def get_cost_summary(self) -> str:
        """返回费用摘要字符串。"""
        return (f"LLM 交互 {self.call_count} 轮 | "
                f"输入 {self.total_prompt_tokens:,} tokens | "
                f"输出 {self.total_completion_tokens:,} tokens | "
                f"费用 ¥{self.total_cost:.4f}")

    def chat(self, prompt: str, user_message: str,
             json_mode: bool = False, use_memory: Optional[bool] = None) -> str:

        self._compress_history()
        self._save_memory()

        messages = [{"role": "system", "content": prompt}]

        if self.history:
            start = max(0, len(self.history) - (self.context_window * 2))
            start = self._snap_to_valid_start(start)
            messages.extend(self.history[start:])

        messages.append({"role": "user", "content": user_message})

        # 清理孤儿 tool 消息
        messages = self._clean_orphan_tools(messages)

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
        self._track_usage(getattr(response, 'usage', None))

        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": content})
        # 写入独立历史日志
        self.last_system_prompt = prompt
        if self.log_history:
            self.logger.log(f"\n{'='*60}\n[{self.call_count}] SYSTEM:\n{prompt[:self.logger.LOG_LLM_PROMPT]}\n\n"
                            f"[{self.call_count}] USER:\n{user_message[:self.logger.LOG_LLM_INTERACT]}\n\n"
                            f"[{self.call_count}] ASSISTANT:\n{content[:self.logger.LOG_RAW_RESPONSE]}")

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
        # 入口落盘保留完整历史记录，防止孤儿tool
        self._compress_history()
        self._save_memory()

        messages = [{"role": "system", "content": prompt}]

        if self.history:
            start = max(0, len(self.history) - (self.context_window * 2))
            start = self._snap_to_valid_start(start)
            messages.extend(self.history[start:])

        messages.append({"role": "user", "content": user_message})

        # 清理孤儿 tool 消息
        messages = self._clean_orphan_tools(messages)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools": tools,
            "tool_choice": "auto",
        }
        self.last_system_prompt = prompt
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            self.logger.log(f"❌ API调用失败: {e}")
            return {"type": "error", "message": f"LLM API错误: {e}"}

        msg = response.choices[0].message
        reasoning = getattr(msg, "reasoning_content", None) or ""
        self.call_count += 1

        self._track_usage(getattr(response, 'usage', None))
        # 记录用户消息
        if self.log_history:
            self.logger.log(f"\n{'='*60}\n[{self.call_count}] TOOLS USER:\n{user_message[:self.logger.LOG_LLM_INTERACT]}")

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
                    if self.log_history:
                        self.logger.log(f"❌ {error_msg}\n"
                                        f"原始参数: {tc.function.arguments}")
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
            if self.log_history:
                lines = [f"[{self.call_count}] TOOLS CALL\n"]
                for c in calls:
                    lines.append(f"  → {c['name']}[{c['id']}]({json.dumps(c['args'], ensure_ascii=False)})\n")
                self.logger.log(''.join(lines))

            # 更新历史（包括工具调用消息）
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
            result = {"type": "tool_calls", "calls": calls, "reasoning_content": reasoning}

        else:
            # ---------- 普通文本回复 ----------
            content = msg.content or ""
            self.last_raw_response = content
            if self.log_history:
                self.logger.log(f"[{self.call_count}] TOOLS ASSISTANT:\n{content[:self.logger.LOG_RAW_RESPONSE]}")
            self.history.append({"role": "user", "content": user_message})
            self.history.append({"role": "assistant", "content": content})
            result = {"type": "text", "content": content, "reasoning_content": reasoning}

        return result

    def _compress_history(self):
        """历史压缩：当 history 条数超过 context_window-3 时，压缩旧的对话为总结。

        流程：
        1. 将已有历史（含上一轮总结）送入 LLM 生成新总结，上一轮总结始终在上下文中保证积累
        2. 总结 + 最近 half 条写入 memory_file（覆盖模式）
        3. history 替换为 [总结] + [最近 half 条]
        4. 后续每经过 half 条新记录，触发新一轮压缩
        """
        if not self.memory_file:
            return

        threshold = self.context_window - 3
        # half = max(1, self.context_window // 2)
        hold_items = max(1, self.context_window // 3)

        total = len(self.history)

        if total <= threshold:
            return

        # 找到已有的总结位置（如果有的话）
        summary_pos = -1
        for i, entry in enumerate(self.history):
            content_val = entry.get("content", "")
            if isinstance(content_val, str) and content_val.startswith("[上下文总结]"):
                summary_pos = i
                break

        # 从上一轮总结后开始（不含总结本身），上一轮总结会重新传入
        to_summarize = self.history[summary_pos+1:] if summary_pos >= 0 else self.history
        new_count = len(to_summarize)

        if new_count <= threshold:
            return  # 还不够一轮压缩

        # 调用 LLM 生成总结
        msgs = [{"role": "system", "content": history_context_summary_prompt}]
        msgs.extend(to_summarize)
        msgs.append({"role": "user", "content": f"根据系统提示词生成增量信息,并将增量信息或修改变更添加到如下总结当中:\n{self.history_compress_summary}\n直接返回总结后的快照结果，不要任何其他信息"})

        try:
            resp = self.client.chat.completions.create(
                model=self.model, messages=msgs,
                temperature=0.1, max_tokens=4096,
            )
            summary = resp.choices[0].message.content or ""
            self._track_usage(getattr(resp, 'usage', None))
        except Exception as e:
            if self.logger:
                self.logger.log(f"[WARN] 历史压缩失败: {e}")
            return

        # 保留最近的 half 条
        keep_start = max(0, len(to_summarize) - hold_items)
        # 跳过前导 tool 消息，防止 assistant(tool_calls) 被截断后剩下孤儿 tool
        while keep_start < len(to_summarize) and to_summarize[keep_start].get("role") == "tool":
            keep_start += 1
        recent = to_summarize[keep_start:]

        # 构建新 history: 总结 + 近期条目
        summary_entry = {"role": "user", "content": f"[上下文总结]\n{summary}"}
        self.history = [summary_entry] + recent
        self.history_compress_summary = summary_entry["content"]
        if self.logger:
            self.logger.log(f"最新[历史压缩]结果: {self.history_compress_summary}")        # 写回 memory_file（覆盖模式）
        try:
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                for entry in self.history:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            if self.logger:
                self.logger.log(f"[WARN] 保存压缩记忆失败: {e}")

        self._last_saved_count = len(self.history)
        if self.logger:
            self.logger.log(f"[历史压缩] {new_count} 条 → 1 条总结 + {len(recent)} 条最近记录")


    @staticmethod
    def _clean_orphan_tools(messages: list) -> list:
        """移除 history 中孤儿 tool 消息（无匹配 assistant with tool_calls 的 tool 消息）。"""
        valid = []
        pending_ids = set()
        for m in messages:
            role = m.get("role", "")
            if role == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    pending_ids.add(tc["id"])
                valid.append(m)
            elif role == "tool":
                tid = m.get("tool_call_id", "")
                if tid in pending_ids:
                    valid.append(m)
                    pending_ids.discard(tid)
                # else: skip orphan tool message
            else:
                valid.append(m)
        return valid

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

    def _load_memory(self):
        """从 memory_file（JSONL 格式）加载历史记录。"""
        self.history_compress_summary = ""
        if not self.memory_file:
            return
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    self.history = [json.loads(line) for line in f if line.strip()]
                # 提取最新的上下文总结
                for entry in reversed(self.history):
                    content_val = entry.get("content", "")
                    if isinstance(content_val, str) and content_val.startswith("[上下文总结]"):
                        self.history_compress_summary = content_val
                        break
        except Exception as e:
            print(f"[WARN] 加载记忆文件失败: {e}", file=sys.stderr)

    def _save_memory(self):
        """增量追加新增的 history 条目到 memory_file（JSONL 格式）。"""
        if not self.memory_file:
            return
        try:
            new_entries = self.history[self._last_saved_count:]
            if not new_entries:
                return
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            with open(self.memory_file, "a", encoding="utf-8") as f:
                for entry in new_entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._last_saved_count = len(self.history)
        except Exception as e:
            print(f"[WARN] 保存记忆文件失败: {e}", file=sys.stderr)

    def dump_history(self, filepath: str = ""):
        """导出当前历史记录到文件，方便调试（包含系统提示词）。

        Args:
            filepath: 输出路径，默认 <log_dir>/history_dump_<timestamp>.json
        """
        import json
        if not filepath:
            import time
            ts = time.strftime("%Y%m%d_%H%M%S")
            log_dir = self.logger._log_dir if self.logger and getattr(self.logger, "_log_dir", "") else "."
            filepath = os.path.join(log_dir, f"history_dump_{ts}.json")
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        # 将系统提示词放在最前面
        full_history = []
        if self.last_system_prompt:
            full_history.append({"role": "system", "content": self.last_system_prompt})
        full_history.extend(self.history)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(full_history, f, ensure_ascii=False, indent=2)
        return filepath

    def submit_tool_result(self, tool_call_id: str, result: str):
        """将函数执行结果追加到 hisry，供 LLM 下一轮使用"""
        if len(result) > MAX_HISTORY_CONTENT:
            result = (f"[内容过长已截断，原 {len(result)} 字符]\n"
                      f"{result[:MAX_HISTORY_CONTENT]}\n"
                      f"[... 省略 {len(result) - MAX_HISTORY_CONTENT} 字符 ...]")
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        })
        if self.log_history:
            self.logger.log(f"  TOOL RESULT[{tool_call_id}] :\n{result[:self.logger.LOG_EXEC_OUTPUT]}")

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
