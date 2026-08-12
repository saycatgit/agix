#!/usr/bin/env python3
"""跨平台 portable 打包脚本 — 内置 Flet 客户端，免首次下载

产物命名: agix-{version}-{platform}（裸二进制，不打 zip）
与 build_portable.py 的区别：
  - 将 Flet 桌面客户端 tar.gz/zip 通过 --add-data 注入 flet_desktop/app/
  - 运行时 ensure_client_cached() 自动从内置归档解压，跳过网络下载
  - 用户首次启动即用，节省约 60~120 秒下载时间

用法:
    python build_portable_flet.py              # 普通打包 + 内置 Flet 客户端
    python build_portable_flet.py --cython     # Cython + 内置 Flet 客户端
    python build_portable_flet.py --clean      # 清理所有构建缓存

依赖: PyInstaller、Cython（仅 --cython 模式）、C 编译器
"""

import os
import sys
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

# 确保能 import 同目录的 build_portable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_portable import (  # noqa: E402
    PROJECT_ROOT, SRC_DIR, INNER_SPACE, WORKSPACE,
    RELEASE_DIR, BUILD_DIR, CYTHON_BUILD_DIR,
    ENTRY_MODULE, EXCLUDE_MODULES, CYTHON_HIDDEN_IMPORTS,
    find_pyinstaller, cython_compile, _collect_add_data_files,
)

# 版本号
try:
    from version import APP_VERSION
except ImportError:
    APP_VERSION = "0.0.0"


def _get_platform_tag():
    """返回当前平台标识，用于产物命名"""
    import platform as _plat
    if os.name == "nt":
        return "win-x64"
    elif sys.platform == "darwin":
        return f"macos-{_plat.machine()}"
    else:
        return f"linux-{_plat.machine()}"


PLATFORM_TAG = _get_platform_tag()

# Flet 客户端归档下载源
FLET_CLIENT_BASE = "http://www.agix.cc/deps/flet"


def _get_flet_artifact_info():
    """返回 (下载URL, 归档文件名)"""
    import flet_desktop
    artifact = flet_desktop.get_artifact_filename()
    ver = flet_desktop.version.version
    url = f"{FLET_CLIENT_BASE}/v{ver}/{artifact}"
    return url, artifact


def _download_flet_archive(url, artifact, dest_dir):
    """下载 Flet 客户端归档，返回本地路径"""
    dest = Path(dest_dir) / artifact
    if dest.exists():
        print(f"   ✓ 已存在: {dest}")
        return dest

    print(f"   ⬇ 下载 {artifact} ...")
    print(f"      {url}")
    urllib.request.urlretrieve(url, str(dest))

    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"   ✓ 下载完成 ({size_mb:.1f} MB)")
    return dest


def build_flet(clean=False, use_cython=False):
    pyinstaller = find_pyinstaller()
    separator = ";" if os.name == "nt" else ":"
    exe_suffix = ".exe" if os.name == "nt" else ""

    if clean:
        for d in [BUILD_DIR, RELEASE_DIR, CYTHON_BUILD_DIR]:
            if d.exists():
                print(f"🧹 清理 {d}")
                shutil.rmtree(d)

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 下载 Flet 客户端归档
    print("\n📦 Flet 客户端内置")
    url, artifact = _get_flet_artifact_info()
    tmpdir = Path(tempfile.gettempdir()) / "agix_build_flet"
    tmpdir.mkdir(parents=True, exist_ok=True)
    flet_archive = _download_flet_archive(url, artifact, tmpdir)

    # 2. Cython 编译（可选）
    if use_cython:
        src_for_build = cython_compile()
        entry_script = src_for_build / f"{ENTRY_MODULE}.py"
    else:
        src_for_build = SRC_DIR
        entry_script = SRC_DIR / f"{ENTRY_MODULE}.py"

    # 3. --add-data（逐个文件 + Flet 归档）
    add_data_items = _collect_add_data_files(INNER_SPACE, "inner_space", separator)
    add_data_items += _collect_add_data_files(WORKSPACE, "workspace", separator)
    # Flet 客户端归档 → flet_desktop/app/ (ensure_client_cached 自动识别)
    add_data_items.append(f"{flet_archive}{separator}flet_desktop/app")
    # Flet 图标数据文件（PyInstaller 不会自动收集到临时目录）
    import flet as _flet
    _flet_base = Path(_flet.__path__[0])
    add_data_items.append(
        f"{_flet_base}/controls/material/icons.json{separator}flet/controls/material"
    )
    add_data_items.append(
        f"{_flet_base}/controls/cupertino/cupertino_icons.json{separator}flet/controls/cupertino"
    )
    print(f"📋 资源文件: {len(add_data_items)} 个（含 Flet 客户端归档）")

    # 4. PyInstaller 命令行
    cmd = [
        str(pyinstaller),
        "--onefile",
        "--name", "agix",
        "--workpath", str(BUILD_DIR),
        "--specpath", str(BUILD_DIR),
        "--distpath", str(RELEASE_DIR),
        "--noconfirm",
    ]

    for item in add_data_items:
        cmd.extend(["--add-data", item])

    if clean:
        cmd.append("--clean")

    for mod in EXCLUDE_MODULES:
        cmd.extend(["--exclude-module", mod])

    if use_cython:
        cmd.extend(["--paths", str(src_for_build)])
        for hidden_import in CYTHON_HIDDEN_IMPORTS:
            cmd.extend(["--hidden-import", hidden_import])

    cmd.append(str(entry_script))

    print(f"\n📦 目标平台: {'Windows' if os.name == 'nt' else sys.platform}")
    if use_cython:
        print(f"🔒 源码保护: Cython 编译模式")
    print(f"📦 内置 Flet 客户端: {artifact}")
    print(f"🔧 PyInstaller: {pyinstaller}")
    print(f"🚀 开始打包...")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print(f"❌ 打包失败 (exit={result.returncode})")
        sys.exit(result.returncode)

    product = RELEASE_DIR / f"agix{exe_suffix}"
    if not product.is_file():
        print(f"❌ 产物缺失: {product}")
        sys.exit(1)

    size_mb = product.stat().st_size / (1024 * 1024)
    print(f"\n✅ 打包完成: {product} ({size_mb:.1f} MB)")

    # 重命名为带版本号的产物（不打 zip，避免 artifact 下载时双 zip）
    final_name = f"agix-{APP_VERSION}-{PLATFORM_TAG}{exe_suffix}"
    final_path = RELEASE_DIR / final_name
    if final_path.exists():
        final_path.unlink()
    product.rename(final_path)
    print(f"✅ 最终产物: {final_path}")


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    use_cython = "--cython" in sys.argv
    build_flet(clean=clean, use_cython=use_cython)
