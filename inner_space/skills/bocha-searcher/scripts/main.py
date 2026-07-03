#!/usr/bin/env python3
"""bocha-searcher —— 使用博查(Bocha) API 搜索互联网资料"""

import argparse
import json
import sys
import os

HAS_REQUESTS = False
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    pass

# 博查 API 密钥（从环境变量或内置默认值读取）
BOCHA_API_KEY = os.environ.get(
    "BOCHA_API_KEY",
    "sk-f5b6060389aa492887b9055445ca2e4b"
)

# 博查 Web Search API 端点
BOCHA_API_ENDPOINT = "https://api.bochaai.com/v1/web-search"


def search_web(query: str, max_results: int = 10) -> list:
    """使用博查 API 搜索网页，返回结果列表"""
    if not query.strip():
        return []

    headers = {
        "Authorization": f"Bearer {BOCHA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "count": max_results,
        "summary": True,
    }

    try:
        resp = requests.post(
            BOCHA_API_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=30,
        )

        if resp.status_code == 200:
            data = resp.json()
            return _parse_response(data)
        elif resp.status_code == 401:
            return [{"error": "API 密钥无效 (401 Unauthorized)"}]
        elif resp.status_code == 403:
            err_msg = data.get("message", "配额不足或权限不够") if (data := resp.json()) else "403 Forbidden"
            return [{"error": f"请求被拒绝 (403): {err_msg}"}]
        elif resp.status_code == 429:
            return [{"error": "请求频率超限 (429 Too Many Requests)"}]
        else:
            return [{"error": f"HTTP {resp.status_code}: {resp.text[:300]}"}]

    except requests.exceptions.Timeout:
        return [{"error": "请求超时"}]
    except requests.exceptions.ConnectionError:
        return [{"error": "连接失败，请检查网络"}]
    except Exception as e:
        return [{"error": f"未知错误: {str(e)}"}]


def _parse_response(data: dict) -> list:
    """解析博查 API 响应，支持多种格式"""
    # 格式1: {"code": 200, "data": {"webPages": {"value": [...]}}}
    if "code" in data:
        if data["code"] != 200:
            return [{"error": f"API 错误 (code={data['code']}): {data.get('msg', 'unknown')}"}]
        data = data.get("data", data)

    # 格式2: {"_type": "SearchResponse", "webPages": {"value": [...]}}
    web_pages = data.get("webPages", {})
    items = web_pages.get("value", [])

    if not items:
        items = data.get("results", data.get("data", []))

    results = []
    for item in items:
        if isinstance(item, dict):
            results.append({
                "title": item.get("name", item.get("title", "")),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", item.get("summary", "")),
                "site_name": item.get("siteName", ""),
                "date_published": item.get("datePublished", ""),
            })

    return results


def format_text(results: list) -> str:
    """将结果格式化为可读文本"""
    if not results:
        return "(无结果)"
    if results and "error" in results[0]:
        return f"搜索出错: {results[0]['error']}"

    lines = []
    for i, r in enumerate(results, 1):
        site = f" [{r.get('site_name', '')}]" if r.get('site_name') else ""
        lines.append(f"[{i}] {r['title']}{site}")
        lines.append(f"    URL: {r['url']}")
        lines.append(f"    {r['snippet']}")
        if r.get('date_published'):
            lines.append(f"    日期: {r['date_published']}")
        lines.append("")
    return "\n".join(lines).strip()


def main():
    parser = argparse.ArgumentParser(
        description="bocha-searcher —— 使用博查(Bocha) API 搜索互联网资料"
    )
    parser.add_argument("--query", type=str, default="", required=True,
                        help="搜索关键词")
    parser.add_argument("--max_results", type=int, default=10,
                        help="最大结果数（默认 10）")
    parser.add_argument("--format", type=str, default="json",
                        choices=["json", "text"],
                        help="输出格式：json 或 text（默认 json）")
    args = parser.parse_args()

    if not HAS_REQUESTS:
        result = {
            "status": "error",
            "message": "缺少依赖，请执行: pip install requests"
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    results = search_web(args.query, max_results=args.max_results)
    has_error = bool(results and "error" in results[0])

    if args.format == "json":
        output = {
            "status": "error" if has_error else "ok",
            "query": args.query,
            "total": len(results) if not has_error else 0,
            "results": results,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_text(results))

    return 0 if not has_error else 1


if __name__ == "__main__":
    sys.exit(main())
