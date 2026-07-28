# searxng-searcher

使用自部署的SearXNG聚合搜索引擎搜索互联网资料，返回网页标题、摘要和链接

## 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string |  | 搜索关键词 |
| `max_results` | integer | 10 | 最大结果数 |
| `format` | string | json | 输出格式：json 或 text |
| `endpoint` | string | http://8.130.188.188:8080 | SearXNG 服务地址 |

## 调用方式

### CLI 命令行

```bash
python3 /home/agent_native/inner_space/skills/searxng-searcher/scripts/main.py --query <query> --max_results <max_results> --format <format> --endpoint <endpoint>
```

## 示例

```bash
python3 /home/agent_native/inner_space/skills/searxng-searcher/scripts/main.py --query <query> --max_results 10 --format json --endpoint http://8.130.188.188:8080
```

## 文件结构

- `skills/searxng-searcher/skill.json` — 元数据与参数 Schema
- `skills/searxng-searcher/SKILL.md` — skill 说明文档
- `skills/searxng-searcher/scripts/main.py` — skill 主程序
