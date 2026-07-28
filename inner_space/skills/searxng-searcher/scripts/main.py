#!/usr/bin/env python3
"""searxng-searcher —— 使用自部署 SearXNG 聚合搜索引擎搜索互联网"""

import argparse
import html as _html
import re as _re
import json
import sys
import urllib.request
import urllib.error
import urllib.parse

DEFAULT_ENDPOINT = "http://8.130.188.188:8080"


def search_web(query: str, max_results: int = 10, endpoint: str = DEFAULT_ENDPOINT) -> list:
    """通过 SearXNG JSON API 搜索网页，返回结果列表"""
    if not query.strip():
        return []

    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
    })
    url = f"{endpoint}/search?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "searxng-searcher/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = _parse_response(data, max_results)
        return results

    except urllib.error.HTTPError as e:
        return [{"error": f"HTTP {e.code}: {e.reason}"}]
    except urllib.error.URLError as e:
        return [{"error": f"连接失败: {e.reason}"}]
    except json.JSONDecodeError:
        return [{"error": "响应解析失败，非 JSON 格式"}]
    except Exception as e:
        return [{"error": f"未知错误: {str(e)}"}]


def _clean_text(text: str) -> str:
    """清洗文本：去除 HTML 标签、解码实体、合并冗余空白"""
    if not text:
        return ""
    text = _re.sub(r'<[^>]+>', '', text)          # 去 HTML 标签
    text = _html.unescape(text)                    # 解码 &amp; &lt; 等实体
    return _re.sub(r'\s+', ' ', text).strip()      # 合并空白


def _parse_response(data: dict, max_results: int) -> list:
    """解析 SearXNG JSON 响应"""
    raw_results = data.get("results", [])
    if not raw_results:
        return []

    results = []
    for item in raw_results[:max_results]:
        results.append({
            "title": _clean_text(item.get("title", "")),
            "url": item.get("url", "").strip(),
            "snippet": _clean_text(item.get("content", item.get("snippet", ""))),
            "engine": ", ".join(item.get("engines", [])) if isinstance(item.get("engines"), list) else item.get("engine", ""),
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
        engine_tag = f" [{r.get('engine', '')}]" if r.get('engine') else ""
        lines.append(f"[{i}] {r['title']}{engine_tag}")
        lines.append(f"    URL: {r['url']}")
        lines.append(f"    {r['snippet']}")
        lines.append("")
    return "\n".join(lines).strip()


def main():
    parser = argparse.ArgumentParser(
        description="searxng-searcher —— 使用自部署 SearXNG 聚合搜索引擎搜索互联网"
    )
    parser.add_argument("--query", type=str, default="", required=True,
                        help="搜索关键词")
    parser.add_argument("--max_results", type=int, default=10,
                        help="最大结果数（默认 10）")
    parser.add_argument("--format", type=str, default="json",
                        choices=["json", "text"],
                        help="输出格式：json 或 text（默认 json）")
    parser.add_argument("--endpoint", type=str, default=DEFAULT_ENDPOINT,
                        help=f"SearXNG 服务地址（默认 {DEFAULT_ENDPOINT}）")
    args = parser.parse_args()

    results = search_web(args.query, max_results=args.max_results, endpoint=args.endpoint)
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
