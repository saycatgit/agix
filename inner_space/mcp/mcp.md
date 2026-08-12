# MCP 客户端

通过 stdio 协议连接外部 MCP 服务器，调用第三方工具接口。

## 使用方式

通过 `run_shell` 工具调用 `mcp_client.py`，工作目录为 `inner_space/mcp/`：

**列出某服务器的全部工具：**
```
python3 mcp_client.py <server_name> --tools
```

**调用工具（参数以 JSON 传入）：**
```
python3 mcp_client.py <server_name> <tool_name> '{"arg1":"val1","arg2":"val2"}'
```

## 注意事项

- 调用前先用 `--tools` 确认工具名和参数格式
- 参数 JSON 中的经纬度格式统一为 `"经度,纬度"`（逗号分隔字符串）
- 超时设置建议 30 秒以上，Node.js MCP 首次需下载依赖建议 120 秒
- Windows 下 Python 命令为 `python`（非 `python3`）
- 编码问题已在 `mcp_client.py` 中处理（Popen encoding=utf-8 + stdout 容错包装），无需额外操作

## 服务器管理

通过 `mcp_manager.py` 管理 MCP 服务器，工作目录为 `inner_space/mcp/`：

**添加服务器：**
```
python3 mcp_manager.py add '{"name":"<name>","command":"<cmd>","args":[...],"env":{...},"desc":"<说明>"}'
```

**删除服务器：**
```
python3 mcp_manager.py del <server_name>
```

**添加时的特殊说明：**
- 命令路径用完整绝对路径，避免 PATH 问题
- 依赖 Node.js 类工具时，在 `env.PATH` 中显式注入 `C:\Program Files\nodejs` 及系统目录
- 复杂 JSON 配置优先用 `write_file` 直接覆写 `mcp.json`，避免 shell 传参转义

## MCP可用服务器

| 服务器 | 说明 |
|--------|------|
| `amap` | 高德地图：地理编码、逆地理编码、IP定位、天气、POI搜索、驾车/步行/公交/骑行路径规划、距离测量（✅ 已接入可用，12个工具） |
| `bing-search` | Bing搜索 + 网页抓取：`bing_search`（query/count/offset）、`crawl_webpage`（uuids/urlMap）（✅ 已接入可用） |
