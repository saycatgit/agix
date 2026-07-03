#!/usr/bin/env python3
"""skill-finder —— 搜索互联网上的 skill 仓库并拉取到本地"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
import tempfile
import shutil
from pathlib import Path


SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
SKILLS_PATH = str(SKILLS_DIR)
INDEX_FILE = os.path.join(SKILLS_PATH, "skills_index.json")

# 默认 skill 索引源（已知的 skill 仓库列表）
DEFAULT_SOURCES = [
    {
        "name": "agent-skills-collection",
        "url": "https://github.com/codebase-community/agent-skills-collection",
        "description": "Agent Skills 社区集合仓库",
    },
    {
        "name": "awesome-claude-skills",
        "url": "https://github.com/topics/claude-skill",
        "description": "GitHub 上标记为 claude-skill 主题的仓库",
    },
]


def load_index():
    """加载本地 skill 索引"""
    if not os.path.exists(INDEX_FILE):
        return []
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_index(index: list):
    """保存本地 skill 索引"""
    os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def search_github(query: str, max_results: int = 20) -> list:
    """通过 GitHub REST API 搜索包含 skill 主题的仓库"""
    results = []
    # 搜索组合：skill 相关 topic + 用户关键词
    search_queries = [
        f"topic:skill+{query}",
        f"topic:claude-skill+{query}",
        f"topic:agent-skill+{query}",
        f"skill+{query}+in:name,description",
    ]

    for sq in search_queries[:2]:  # 限制搜索次数避免 API 限流
        try:
            url = f"https://api.github.com/search/repositories?q={sq}&sort=stars&order=desc&per_page={max_results}"
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("User-Agent", "skill-finder/1.0")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                for item in data.get("items", []):
                    results.append({
                        "name": item.get("full_name", ""),
                        "url": item.get("html_url", ""),
                        "description": item.get("description", ""),
                        "stars": item.get("stargazers_count", 0),
                        "topics": item.get("topics", []),
                        "source": "github",
                    })
        except urllib.error.HTTPError as e:
            if e.code == 403:
                # 限流，尝试无认证也能获取一些结果
                continue
        except Exception:
            continue

    # 去重
    seen = set()
    unique = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    return unique[:max_results]


def search_local(query: str) -> list:
    """在本地已安装的 skill 中搜索"""
    index = load_index()
    if not query:
        return index
    q = query.lower()
    results = []
    for skill in index:
        name = skill.get("name", "").lower()
        desc = skill.get("description", "").lower()
        if q in name or q in desc:
            results.append(skill)
    return results


def search_default_sources(query: str) -> list:
    """在默认 skill 源中搜索匹配项"""
    results = []
    q = query.lower() if query else ""
    for src in DEFAULT_SOURCES:
        if not q or q in src["name"].lower() or q in src["description"].lower():
            results.append({
                "name": src["name"],
                "url": src["url"],
                "description": src["description"],
                "source": "default-index",
            })
    return results


def do_search(query: str, source: str = "", output_json: bool = True) -> dict:
    """执行搜索操作"""
    all_results = []

    # 1. 搜索默认源
    all_results.extend(search_default_sources(query))

    # 2. 搜索本地已安装 skill
    local = search_local(query)
    for l in local:
        l["source"] = "local"
        all_results.append(l)

    # 3. GitHub 搜索
    if query:
        gh_results = search_github(query)
        all_results.extend(gh_results)

    return {
        "status": "ok",
        "action": "search",
        "query": query,
        "total": len(all_results),
        "results": all_results,
    }


def clone_repo(url: str, target_dir: str) -> dict:
    """使用 git clone 拉取仓库"""
    cmd = ["git", "clone", "--depth", "1", url, target_dir]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "method": "git-clone", "target": target_dir}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "clone 超时"}
    except FileNotFoundError:
        return {"ok": False, "error": "git 不可用"}


def download_archive(url: str, target_dir: str) -> dict:
    """下载 tar.gz 归档并解压（GitHub 仓库备选方案）"""
    try:
        os.makedirs(target_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            urllib.request.urlretrieve(url, tmp_path)
            shutil.unpack_archive(tmp_path, target_dir, "gztar")
            return {"ok": True, "method": "download", "target": target_dir}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def install_skill_from_dir(src_dir: str, skill_name: str) -> dict:
    """从拉取的目录中安装 skill 到 skills/ 目录"""
    src_path = Path(src_dir)
    if not src_path.exists():
        return {"ok": False, "error": f"源目录不存在: {src_dir}"}

    # 查找 skill.json 或 SKILL.md
    skill_files = list(src_path.rglob("skill.json"))
    if not skill_files:
        # 可能仓库本身就是 skill 目录
        if (src_path / "skill.json").exists():
            skill_files = [src_path / "skill.json"]
        elif (src_path / "SKILL.md").exists():
            # 有 SKILL.md 就可以
            pass
        else:
            return {"ok": False, "error": "未找到 skill.json 或 SKILL.md，可能不是有效的 skill 仓库"}

    # 确定 skill 名称
    target_skill_name = skill_name
    if skill_files:
        try:
            with open(skill_files[0], "r", encoding="utf-8") as f:
                meta = json.load(f)
            target_skill_name = meta.get("name", skill_name)
        except Exception:
            pass

    target_dir = os.path.join(SKILLS_PATH, target_skill_name)

    # 如果目标是仓库根目录，复制整个仓库内容到 skills/<name>/
    if skill_files and skill_files[0].parent != src_path:
        src_dir = str(skill_files[0].parent)

    try:
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(src_dir, target_dir, dirs_exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": f"复制失败: {e}"}

    # 更新 skills_index.json
    skill_json_path = os.path.join(target_dir, "skill.json")
    if os.path.exists(skill_json_path):
        try:
            with open(skill_json_path, "r", encoding="utf-8") as f:
                skill_meta = json.load(f)
            index = load_index()
            # 更新或追加
            existing = [i for i, s in enumerate(index) if s.get("name") == target_skill_name]
            entry = {
                "name": target_skill_name,
                "description": skill_meta.get("description", ""),
                "md_path": os.path.join(target_dir, "SKILL.md"),
                "schema": skill_meta.get("schema", {}),
                "entrypoint": skill_meta.get("entrypoint", ""),
                "invoke": skill_meta.get("invoke", "cli"),
            }
            if existing:
                index[existing[0]] = entry
            else:
                index.append(entry)
            save_index(index)
        except Exception as e:
            return {"ok": False, "error": f"更新索引失败: {e}"}

    return {"ok": True, "skill_name": target_skill_name, "target": target_dir}


def do_pull(url: str, name: str = "", output_json: bool = True) -> dict:
    """执行拉取操作"""
    if not url:
        return {"status": "error", "message": "pull 操作需要指定 --source（仓库 URL）"}

    skill_name = name or url.rstrip("/").split("/")[-1].replace(".git", "")

    with tempfile.TemporaryDirectory(prefix="skill_finder_") as tmp_dir:
        # 先用 git clone
        clone_result = clone_repo(url, tmp_dir)

        if not clone_result["ok"]:
            # git clone 失败，尝试下载 archive
            archive_url = ""
            if "github.com" in url:
                # 尝试 GitHub archive
                clean_url = url.rstrip("/").replace(".git", "")
                archive_url = f"{clean_url}/archive/refs/heads/main.tar.gz"

            if archive_url:
                clone_result = download_archive(archive_url, tmp_dir)
            else:
                return {"status": "error", "message": f"拉取失败: {clone_result['error']}"}

        if not clone_result["ok"]:
            return {"status": "error", "message": f"拉取失败: {clone_result['error']}"}

        # 安装 skill
        install_result = install_skill_from_dir(tmp_dir, skill_name)
        if not install_result["ok"]:
            return {"status": "error", "message": f"安装失败: {install_result['error']}"}

        return {
            "status": "ok",
            "action": "pull",
            "skill_name": install_result["skill_name"],
            "target": install_result["target"],
            "message": f"skill '{install_result['skill_name']}' 已安装到 {install_result['target']}",
        }


def main():
    parser = argparse.ArgumentParser(description="skill-finder —— 搜索并拉取互联网上的 skill")
    parser.add_argument("--query", type=str, default="", help="搜索关键词")
    parser.add_argument("--action", type=str, default="search",
                        choices=["search", "pull"], help="操作类型")
    parser.add_argument("--source", type=str, default="", help="仓库 URL（pull 时必填）")
    parser.add_argument("--name", type=str, default="", help="skill 名称（pull 时可选）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args()

    use_json = args.json or os.environ.get("SKILL_FINDER_JSON", "")

    if args.action == "search":
        result = do_search(args.query, args.source, output_json=True)
    elif args.action == "pull":
        result = do_pull(args.source, args.name, output_json=True)
    else:
        result = {"status": "error", "message": f"未知操作: {args.action}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
