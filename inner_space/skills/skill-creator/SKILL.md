# skill-creator

创建新的 skill：自动生成目录结构、SKILL.md 文档、skill.json 元数据和 Python 脚本模板。

支持通过 `--mcp` 参数指定新 skill 的通信方式：
- 默认（无 `--mcp`）：生成 CLI 模式的 skill
- `--mcp`：生成 MCP stdio 模式的 skill

## 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | string | (必填) | 新 skill 的名称，如 `my-skill` |
| `description` | string | (必填) | skill 功能描述 |
| `author` | string | "agent" | 作者名称 |
| `params` | string | "" | JSON 格式的参数 Schema，空字符串表示无参数 |
| `mcp` | flag | false | 是否创建 MCP stdio 模式的 skill |

## 调用方式

```bash
python3 /home/agent_native/inner_space/skills/skill-creator/scripts/create_skill.py \
  --name <skill名称> \
  --description "<描述>" \
  --author <作者> \
  --params '<JSON参数Schema>' \
  [--mcp]
```

## 示例

```bash
# 创建 CLI 模式的 skill
python3 /home/agent_native/inner_space/skills/skill-creator/scripts/create_skill.py \
  --name "my-tool" \
  --description "我的自定义工具"

# 创建带参数的 CLI skill
python3 /home/agent_native/inner_space/skills/skill-creator/scripts/create_skill.py \
  --name "greeter" \
  --description "问候工具" \
  --params '{"name":{"type":"string","description":"要问候的名字","default":"World"}}'

# 创建 MCP stdio 模式的 skill（含完整的 JSON-RPC 服务端骨架）
python3 /home/agent_native/inner_space/skills/skill-creator/scripts/create_skill.py \
  --name "my-mcp-tool" \
  --description "MCP 通信工具" \
  --mcp
```

## 生成的文件

- `skills/<name>/skill.json` — 元数据与参数 Schema（⚠️ 字段名严禁修改）
- `skills/<name>/SKILL.md` — skill 说明文档
- `skills/<name>/scripts/main.py` — skill 主程序（MCP 模式含 JSON-RPC 服务端骨架）
