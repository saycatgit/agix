#!/usr/bin/env python3
"""
MCP (Model Context Protocol) stdio 客户端。
从 mcp.json 读取服务器配置，启动子进程通过 stdin/stdout 进行 JSON-RPC 通信。
"""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Optional


class MCPError(Exception):
    """MCP 协议错误。"""
    pass


class MCPClient:
    """MCP stdio 客户端，管理与一个 MCP 服务器的连接。"""

    def __init__(self, command: str, args: list[str] | None = None,
                 env: dict[str, str] | None = None, cwd: str | None = None):
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._pending: dict[int, threading.Event] = {}
        self._responses: dict[int, dict] = {}
        self._server_info: dict = {}
        self._server_capabilities: dict = {}

    # ── 连接管理 ──

    def connect(self) -> None:
        """启动 MCP 服务器子进程并完成初始化握手。"""
        merged_env = os.environ.copy()
        if self.env:
            merged_env.update(self.env)

        self._process = subprocess.Popen(
            [self.command] + self.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
            cwd=self.cwd,
            text=True, 
            encoding="utf-8",
            bufsize=1,
        )
        # 启动后台线程读取 stderr
        threading.Thread(target=self._read_stderr, daemon=True).start()
        # 启动后台线程读取 stdout 响应
        threading.Thread(target=self._read_responses, daemon=True).start()
        # MCP 初始化握手
        self._initialize()

    def close(self) -> None:
        """关闭与 MCP 服务器的连接。"""
        if self._process:
            try:
                self._process.stdin.close()
                self._process.stdout.close()
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    # ── 核心协议方法 ──

    def send_request(self, method: str, params: dict | None = None) -> dict:
        """发送 JSON-RPC 请求并等待响应。"""
        with self._lock:
            self._request_id += 1
            rid = self._request_id

        request = {
            "jsonrpc": "2.0",
            "id": rid,
            "method": method,
            "params": params or {},
        }
        self._send_message(request)

        event = threading.Event()
        self._pending[rid] = event
        event.wait(timeout=30)
        self._pending.pop(rid, None)

        response = self._responses.pop(rid, None)
        if response is None:
            raise MCPError(f"请求超时: method={method}")
        if "error" in response:
            err = response["error"]
            raise MCPError(f"服务器返回错误: code={err.get('code')}, message={err.get('message')}")
        return response.get("result", {})

    def send_notification(self, method: str, params: dict | None = None) -> None:
        """发送 JSON-RPC 通知（不需要响应）。"""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        self._send_message(message)

    # ── MCP 协议接口 ──

    def list_tools(self) -> list[dict]:
        """列出服务器提供的所有工具。"""
        result = self.send_request("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用指定工具。"""
        result = self.send_request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })
        content = result.get("content", [])
        # 提取文本内容
        texts = []
        for item in content:
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif item.get("type") == "resource":
                texts.append(json.dumps(item.get("resource", {})))
        return "\n".join(texts) if texts else content

    def list_resources(self) -> list[dict]:
        """列出服务器提供的资源。"""
        result = self.send_request("resources/list")
        return result.get("resources", [])

    def read_resource(self, uri: str) -> dict:
        """读取指定资源内容。"""
        return self.send_request("resources/read", {"uri": uri})

    def list_prompts(self) -> list[dict]:
        """列出服务器提供的提示模板。"""
        result = self.send_request("prompts/list")
        return result.get("prompts", [])

    def get_prompt(self, name: str, arguments: dict[str, str] | None = None) -> dict:
        """获取指定提示模板内容。"""
        return self.send_request("prompts/get", {
            "name": name,
            "arguments": arguments or {},
        })

    # ── 内部方法 ──

    def _initialize(self) -> None:
        """MCP 初始化握手：initialize → initialized。"""
        result = self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "agix-mcp-client",
                "version": "1.0.0",
            },
        })
        self._server_info = result.get("serverInfo", {})
        self._server_capabilities = result.get("capabilities", {})
        self.send_notification("notifications/initialized")

    def _send_message(self, message: dict) -> None:
        """写入一行 JSON 到子进程 stdin。"""
        if not self._process or not self._process.stdin:
            raise MCPError("MCP 服务器未连接")
        line = json.dumps(message, ensure_ascii=False) + "\n"
        self._process.stdin.write(line)
        self._process.stdin.flush()

    def _read_responses(self) -> None:
        """后台线程：持续读取 stdout 的 JSON-RPC 响应并分发。"""
        if not self._process or not self._process.stdout:
            return
        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = msg.get("id")
            if rid is not None and rid in self._pending:
                self._responses[rid] = msg
                self._pending[rid].set()

    def _read_stderr(self) -> None:
        """后台线程：读取 stderr 并输出到控制台。"""
        if not self._process or not self._process.stderr:
            return
        for line in self._process.stderr:
            sys.stderr.write(f"[MCP stderr] {line}")
            sys.stderr.flush()


# ── 配置加载 ──

def load_servers(config_path: str | None = None) -> dict[str, dict]:
    """从 mcp.json 加载所有服务器配置。"""
    if config_path is None:
        config_path = Path(__file__).parent / "mcp.json"
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("servers", {})


def create_client(server_name: str, config_path: str | None = None) -> MCPClient:
    """根据服务器名称创建 MCPClient 实例。"""
    servers = load_servers(config_path)
    if server_name not in servers:
        available = ", ".join(servers.keys()) or "(无)"
        raise MCPError(f"未找到服务器 '{server_name}'，可用: {available}")
    cfg = servers[server_name]
    return MCPClient(
        command=cfg["command"],
        args=cfg.get("args", []),
        env=cfg.get("env"),
        cwd=cfg.get("cwd"),
    )


# ── CLI 入口 ──

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python mcp_client.py <server_name> [工具名] [参数JSON]")
        print("       python mcp_client.py <server_name> --tools")
        print("       python mcp_client.py <server_name> --resources")
        print("       python mcp_client.py <server_name> --prompts")
        sys.exit(1)

    server_name = sys.argv[1]
    client = create_client(server_name)

    try:
        client.connect()

        if len(sys.argv) >= 3 and sys.argv[2] == "--tools":
            tools = client.list_tools()
            print(json.dumps(tools, ensure_ascii=False, indent=2))
        elif len(sys.argv) >= 3 and sys.argv[2] == "--resources":
            resources = client.list_resources()
            print(json.dumps(resources, ensure_ascii=False, indent=2))
        elif len(sys.argv) >= 3 and sys.argv[2] == "--prompts":
            prompts = client.list_prompts()
            print(json.dumps(prompts, ensure_ascii=False, indent=2))
        elif len(sys.argv) >= 3:
            tool_name = sys.argv[2]
            tool_args = {}
            if len(sys.argv) >= 4:
                tool_args = json.loads(sys.argv[3])
            result = client.call_tool(tool_name, tool_args)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 默认列出工具
            tools = client.list_tools()
            print(json.dumps(tools, ensure_ascii=False, indent=2))
    finally:
        client.close()
