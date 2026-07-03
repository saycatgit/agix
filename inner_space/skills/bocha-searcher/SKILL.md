# bocha-searcher

使用博查（Bocha）AI Web Search API 搜索互联网资料，返回网页标题、摘要和链接。

## 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | (必填) | 搜索关键词 |
| `max_results` | integer | 10 | 最大返回结果数 |
| `format` | string | json | 输出格式：`json` 或 `text` |

## 调用示例

```bash
# JSON 输出（推荐，供 agent 解析）
python3 /home/agent_native/inner_space/skills/bocha-searcher/scripts/main.py \
  --query "machine learning" --max_results 5 --format json

# 纯文本输出（人类阅读）
python3 /home/agent_native/inner_space/skills/bocha-searcher/scripts/main.py \
  --query "machine learning" --max_results 5 --format text
```

## JSON 输出格式

```json
{
  "status": "ok",
  "query": "machine learning",
  "total": 5,
  "results": [
    {
      "title": "Machine Learning - Wikipedia",
      "url": "https://en.wikipedia.org/wiki/Machine_learning",
      "snippet": "Machine learning is a subset of artificial intelligence...",
      "site_name": "Wikipedia",
      "date_published": "2024-01-01T00:00:00+08:00"
    }
  ]
}
```

## 依赖

- `requests` (pip install requests)

## API 配置

- **端点**: `https://api.bochaai.com/v1/web-search`
- **认证**: `Authorization: Bearer <API_KEY>`
- **API Key**: 已内置，也可通过环境变量 `BOCHA_API_KEY` 覆盖

## 文件结构

- `skills/bocha-searcher/skill.json` — 元数据与参数 Schema
- `skills/bocha-searcher/SKILL.md` — 本文档
- `skills/bocha-searcher/scripts/main.py` — 搜索主程序
