#!/usr/bin/env python3
"""Flet Web 构建脚本 —— 输出静态文件并打包为 zip

用法:
    python build_web.py              # 构建 Web 版本
    python build_web.py --clean      # 清理后构建

产物: release/agix_web.zip（解压后放到 Nginx 即可运行）
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
RELEASE_DIR = PROJECT_ROOT / "release"
WEB_BUILD_DIR = SRC_DIR / "build" / "web"
ENTRY_SCRIPT = "run_web.py"

# Nginx 部署路径前缀（与 Nginx location 匹配）
BASE_URL = "/agix/web/"


def build_web(clean=False):
    if clean:
        for d in [WEB_BUILD_DIR]:
            if d.exists():
                print(f"🧹 清理 {d}")
                shutil.rmtree(d)

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    entry = SRC_DIR / ENTRY_SCRIPT
    if not entry.exists():
        print(f"❌ 入口文件不存在: {entry}")
        sys.exit(1)

    print(f"\n🌐 Flet Web 构建")
    print(f"   入口: {entry}")
    print(f"   基础路径: {BASE_URL}")

    cmd = [
        "flet", "build", "web",
        str(SRC_DIR),
        "--module-name", "run_web",
        "--base-url", BASE_URL,
    ]

    print(f"🚀 开始构建...")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print(f"❌ 构建失败 (exit={result.returncode})")
        sys.exit(result.returncode)

    if not WEB_BUILD_DIR.exists():
        print(f"❌ 构建产物目录不存在: {WEB_BUILD_DIR}")
        sys.exit(1)

    # 打包为 zip
    zip_path = RELEASE_DIR / "agix_web.zip"
    print(f"\n📦 打包 {WEB_BUILD_DIR} → {zip_path}")

    # 删除旧 zip
    if zip_path.exists():
        zip_path.unlink()

    shutil.make_archive(
        str(zip_path.with_suffix("")),
        "zip",
        str(WEB_BUILD_DIR),
    )

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\n✅ Web 构建完成: {zip_path} ({zip_size_mb:.1f} MB)")


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    build_web(clean=clean)
