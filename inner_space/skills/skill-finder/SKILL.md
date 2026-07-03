# skill-finder

搜索互联网上的 skill 仓库，根据用户需求匹配并展示 skill 列表，支持用户选择性拉取到本地。

核心功能：
- **search**：从默认索引源 + GitHub API 搜索匹配的 skill 仓库
- **pull**：通过 git clone（或下载 archive）拉取指定仓库到本地 skills/ 目录，自动注册到 skills_index.json

## 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | "" | 搜索关键词，用于匹配 skill |
| `action` | string | "search" | 操作类型：`search`（搜索）或 `pull`（拉取） |
| `source` | string | "" | 仓库 URL（pull 时必填，search 时可选指定特定源） |
| `name` | string | "" | skill 名称（pull 时可选，默认从 URL 提取） |
| `json` | flag | false | 始终以 JSON 格式输出（默认即 JSON） |

## 调用方式

### CLI 命令行

```bash
# 搜索 skill
python3 /home/agent_native/inner_space/skills/skill-finder/scripts/main.py \
  --action search --query "image"

# 拉取 skill
python3 /home/agent_native/inner_space/skills/skill-finder/scripts/main.py \
  --action pull --source "https://github.com/user/some-skill"
```

## 示例

### 搜索示例

```bash
python3 /home/agent_native/inner_space/skills/skill-finder/scripts/main.py \
  --action search --query "pdf"
```

输出：
```json
{
  "status": "ok",
  "action": "search",
  "query": "pdf",
  "total": 5,
  "results": [
    {
      "name": "owner/repo-name",
      "url": "https://github.com/owner/repo-name",
      "description": "A skill for PDF processing",
      "stars": 42,
      "topics": ["skill", "pdf"],
      "source": "github"
    }
  ]
}
```

### 拉取示例

```bash
python3 /home/agent_native/inner_space/skills/skill-finder/scripts/main.py \
  --action pull --source "https://github.com/user/pdf-skill"
```

输出：
```json
{
  "status": "ok",
  "action": "pull",
  "skill_name": "pdf-skill",
  "target": "/home/agent_native/inner_space/skills/pdf-skill",
  "message": "skill 'pdf-skill' 已安装到 /home/agent_native/inner_space/skills/pdf-skill"
}
```

## 文件结构

- `skills/skill-finder/skill.json` — 元数据与参数 Schema
- `skills/skill-finder/SKILL.md` — skill 说明文档
- `skills/skill-finder/scripts/main.py` — skill 主程序

## 工作流程

1. **search** 阶段输出匹配的仓库列表（JSON），由上层 agent 展示给用户
2. 用户从列表中选择感兴趣的 skill
3. **pull** 阶段传入选定的仓库 URL，skill-finder 自动：
   - `git clone --depth 1` 拉取仓库
   - 扫描仓库中的 `skill.json`/`SKILL.md`
   - 将 skill 目录复制到 `skills/`
   - 更新 `skills_index.json` 注册新 skill
