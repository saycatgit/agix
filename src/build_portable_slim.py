#!/usr/bin/env python3
"""跨平台 Slim 构建脚本 — 仅打包 Cython 编译源码，不含 Python 解释器与任何第三方依赖

与 build_portable.py / build_portable_flet.py 的区别：
  - 不调用 PyInstaller，产物非单一可执行文件
  - 仅 Cython 编译源码（.so/.pyd）+ inner_space/ + workspace/
  - 运行时由 bootstrap.py 从阿里云下载所有依赖 + Flet 客户端
  - 产物体积远小于 portable 版（~5-10MB vs 130MB）
  - 用户机器需预装 Python 3.12

用法:
    python build_portable_slim.py              # Cython 编译 + tar.gz/zip 打包
    python build_portable_slim.py --clean      # 清理构建缓存

依赖: Cython、C 编译器
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_portable import (  # noqa: E402
    PROJECT_ROOT, SRC_DIR, INNER_SPACE, WORKSPACE,
    RELEASE_DIR, CYTHON_BUILD_DIR,
    ENTRY_MODULE, cython_compile, check_c_compiler,
)

SLIM_RELEASE_NAME = "agix_slim"


def _copy_compiled_retain_structure(src_dir: Path, dest_dir: Path) -> int:
    """复制编译产物和入口 .py，保留目录结构。只复制 .so/.pyd + 入口 .py + __init__.py。
    产物放入 dest_dir/src/，保持源码层级，使 _get_root_path() 的 parent.parent 正确。

    返回 (模块数, 入口路径)。
    """
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)

    module_dest = dest_dir / "src"
    module_dest.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in sorted(src_dir.rglob("*")):
        rel = item.relative_to(src_dir)

        # 跳过编译中间产物
        if item.suffix in (".c", ".pyc"):
            continue
        if "__pycache__" in item.parts:
            continue
        if item.is_dir():
            continue

        # 只保留 .so/.pyd（编译产物）、.py（入口 + __init__）
        if item.is_file() and item.suffix not in (".so", ".pyd", ".py"):
            continue
        # 顶级 .py：仅保留 __init__；入口模块单独处理；子目录 .py 全部保留
        if item.suffix == ".py" and len(rel.parts) == 1 and item.name != "__init__.py":
            continue
        # 跳过构建脚本本身
        if item.name in ("build_portable.py", "build_portable_flet.py", "build_portable_slim.py"):
            continue

        (module_dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, module_dest / rel)
        count += 1

    # 复制入口 .py 到根目录（保持为 .py，方便用户查看/修改）
    entry_src = src_dir / f"{ENTRY_MODULE}.py"
    if entry_src.exists():
        shutil.copy2(entry_src, dest_dir / f"{ENTRY_MODULE}.py")
        count += 1

    return count


def _patch_entry_module(dest_dir: Path):
    """在入口模块 run_flet.py 顶部插入 sys.path 适配，使其能找到 src/ 下的编译产物。"""
    entry_path = dest_dir / f"{ENTRY_MODULE}.py"
    if not entry_path.exists():
        print(f"   ⚠ 入口模块 {entry_path} 不存在，跳过 patch")
        return

    content = entry_path.read_text(encoding="utf-8")
    patch_lines = [
        "# === Slim 包路径适配：编译产物在 src/ 子目录 ===",
        "import sys",
        "from pathlib import Path",
        "_agix_src = Path(__file__).parent / \"src\"",
        "if str(_agix_src) not in sys.path:",
        "    sys.path.insert(0, str(_agix_src))",
        "# ================================================",
        "",
    ]
    preamble = "\n".join(patch_lines)
    new_content = preamble + content
    entry_path.write_text(new_content, encoding="utf-8")
    print(f"   ✓ 已 patch 入口模块: {entry_path}")


def _copy_tree_exclude(src: Path, dest: Path, exclude_patterns: list = None):
    """复制目录树，排除指定模式。"""
    exclude_patterns = exclude_patterns or []
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        skip = False
        for pat in exclude_patterns:
            if item.match(pat):
                skip = True
                break
        if skip:
            continue
        if item.is_dir():
            (dest / rel).mkdir(parents=True, exist_ok=True)
        else:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest / rel)


def _generate_bootstrap(dest_dir: Path):
    """生成 bootstrap.py 启动器。"""
    bootstrap_content = f'''#!/usr/bin/env python3
"""Agix Slim 启动器 — 环境准备 + 启动主程序

解压后运行: python bootstrap.py
负责：检查 Python 版本 → 安装依赖 → 下载 Flet 客户端 → 启动 Agix。
"""

import os
import sys
import subprocess
import platform
import urllib.request
import shutil
from pathlib import Path

AGIX_ROOT = Path(__file__).resolve().parent
BASE_URL = "http://www.agix.cc"
DEPS_URL = f"{{BASE_URL}}/deps/packages"
FLET_BASE = f"{{BASE_URL}}/deps/flet"
FLET_VERSION = "0.85.3"

REQUIRED_PACKAGES = [
    "flet==0.85.3",
    "flet_desktop==0.85.3",
    "openai",
    "cryptography",
    "requests",
    "paramiko",
    "pydantic",
    "httpx",
    "anyio",
    "sniffio",
    "h11",
    "httpcore",
    "certifi",
    "idna",
    "urllib3",
    "charset-normalizer",
    "cffi",
    "pycparser",
    "bcrypt",
    "pynacl",
    "typing-extensions",
    "typing-inspection",
    "tqdm",
    "distro",
    "invoke",
    "oauthlib",
    "repath",
    "jiter",
    "pydantic-core",
    "annotated-types",
    "msgpack",
    "markdown-it-py",
    "prompt-toolkit",
    "debugpy",
]


def get_platform_dir():
    system = platform.system()
    plat_map = {{
        "Linux": "linux_x86_64",
        "Windows": "win_amd64",
        "Darwin": "macosx_arm64",
    }}
    return plat_map.get(system)


def check_python():
    if sys.version_info < (3, 12):
        print(f"需要 Python >= 3.12，当前: {{sys.version}}")
        sys.exit(1)
    print(f"Python {{sys.version_info.major}}.{{sys.version_info.minor}}.{{sys.version_info.micro}} ✓")


def ensure_dependencies():
    plat = get_platform_dir()
    if not plat:
        print(f"未知平台 {{platform.system()}}，跳过依赖安装")
        return

    missing = []
    for pkg_spec in REQUIRED_PACKAGES:
        pkg_name = pkg_spec.split("==")[0].replace("-", "_")
        try:
            __import__(pkg_name)
        except ImportError:
            missing.append(pkg_spec)

    if not missing:
        print("所有依赖已安装 ✓")
        return

    print(f"安装 {{len(missing)}} 个依赖...")
    pip_args = [sys.executable, "-m", "pip", "install", "--quiet", "--no-input"]

    find_url = f"{{DEPS_URL}}/{{plat}}/"
    try:
        subprocess.check_call(
            pip_args + ["--find-links", find_url, "--trusted-host", "www.agix.cc"] + missing,
            timeout=300,
        )
        print("依赖安装完成（阿里云源）✓")
        return
    except Exception as e:
        print(f"阿里云源不可用 ({{e}})，回退 PyPI...")

    try:
        subprocess.check_call(pip_args + missing, timeout=300)
        print("依赖安装完成（PyPI）✓")
    except subprocess.CalledProcessError as e:
        print(f"依赖安装失败: {{e}}")
        print(f"请手动执行: pip install {{' '.join(missing)}}")
        sys.exit(1)


def get_flet_artifact():
    try:
        from flet_desktop import get_artifact_filename
        return get_artifact_filename()
    except Exception:
        system = platform.system()
        if system == "Windows":
            return "flet-windows.zip"
        if system == "Darwin":
            return "flet-macos.tar.gz"
        machine = platform.machine()
        arch_map = {{"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}}
        arch = arch_map.get(machine, machine)
        distro = os.environ.get("FLET_LINUX_DISTRO", "ubuntu24.04")
        return f"flet-linux-{{distro}}-light-{{arch}}.tar.gz"


def ensure_flet_client():
    artifact = get_flet_artifact()
    url = f"{{FLET_BASE}}/v{{FLET_VERSION}}/{{artifact}}"
    home = Path.home()
    cache_base = home / ".flet" / "client" / f"flet-desktop-light-{{FLET_VERSION}}"

    if cache_base.exists() and any(cache_base.iterdir()):
        print("Flet 客户端已缓存 ✓")
        return

    print(f"下载 Flet 客户端: {{artifact}}...")
    cache_base.mkdir(parents=True, exist_ok=True)

    import tempfile
    tmpdir = Path(tempfile.gettempdir()) / "agix_flet_dl"
    tmpdir.mkdir(parents=True, exist_ok=True)
    archive_path = tmpdir / artifact

    try:
        urllib.request.urlretrieve(url, str(archive_path))
    except Exception as e:
        print(f"下载 Flet 客户端失败: {{e}}")
        sys.exit(1)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"已下载 ({{size_mb:.1f}} MB)")

    import tarfile, zipfile
    if artifact.endswith(".tar.gz"):
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(cache_base)
    elif artifact.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(cache_base)

    archive_path.unlink(missing_ok=True)
    shutil.rmtree(tmpdir, ignore_errors=True)
    print("Flet 客户端就绪 ✓")


def run_agix():
    entry = AGIX_ROOT / "{ENTRY_MODULE}.py"
    if not entry.exists():
        print(f"入口文件缺失: {{entry}}")
        sys.exit(1)

    os.environ["FLET_CLIENT_URL"] = (
        f"{{FLET_BASE}}/v{{FLET_VERSION}}/{{get_flet_artifact()}}"
    )

    print("启动 Agix...")
    subprocess.run(
        [sys.executable, str(entry)],
        cwd=str(AGIX_ROOT),
    )


def main():
    print("=" * 40)
    print("  Agix Slim Launcher")
    print("=" * 40)
    check_python()
    ensure_dependencies()
    ensure_flet_client()
    run_agix()


if __name__ == "__main__":
    main()
'''

    bootstrap_path = dest_dir / "bootstrap.py"
    bootstrap_path.write_text(bootstrap_content, encoding="utf-8")
    os.chmod(bootstrap_path, 0o755)
    print("   ✓ bootstrap.py 已生成")


def build_slim(clean: bool = False):
    """构建 Slim 发布包。"""
    if not check_c_compiler():
        print("❌ 需要 C 编译器")
        sys.exit(1)

    if clean:
        for d in [RELEASE_DIR, CYTHON_BUILD_DIR]:
            if d.exists():
                print(f"🧹 清理 {d}")
                shutil.rmtree(d)

    system = platform.system()
    ext_suffix = ".pyd" if system == "Windows" else ".so"

    # 1. Cython 编译
    print("\n🔧 阶段 1/4: Cython 编译源码")
    compiled_src = cython_compile()

    # 2. 组装发布目录
    print("\n📦 阶段 2/4: 组装发布目录")
    slim_dir = RELEASE_DIR / SLIM_RELEASE_NAME
    count = _copy_compiled_retain_structure(compiled_src, slim_dir)
    print(f"   ✓ {count} 个编译产物 → {SLIM_RELEASE_NAME}/")
    _patch_entry_module(slim_dir)

    # 复制 inner_space/
    _copy_tree_exclude(INNER_SPACE, slim_dir / "inner_space", exclude_patterns=[
        "*.pyc", "*__pycache__*", "*.bk", "ssh/.keys/*", "auth_token.json",
    ])
    print("   ✓ inner_space/")

    # 创建空 workspace/
    ws_dest = slim_dir / "workspace"
    ws_dest.mkdir(exist_ok=True)
    (ws_dest / ".gitkeep").touch()
    print("   ✓ workspace/")

    # 3. 生成 bootstrap.py
    print("\n📝 阶段 3/4: 生成 bootstrap.py")
    _generate_bootstrap(slim_dir)

    # 4. 打包
    print("\n📦 阶段 4/4: 打包")
    fmt = "zip" if system == "Windows" else "gztar"
    ext = ".zip" if system == "Windows" else ".tar.gz"
    archive_path = RELEASE_DIR / f"{SLIM_RELEASE_NAME}{ext}"

    print(f"   创建 {archive_path} ...")
    shutil.make_archive(
        str(RELEASE_DIR / SLIM_RELEASE_NAME), fmt,
        root_dir=str(RELEASE_DIR), base_dir=SLIM_RELEASE_NAME,
    )

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"\n✅ Slim 构建完成: {archive_path} ({size_mb:.1f} MB)")
    print(f"   解压后运行: python bootstrap.py")


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    build_slim(clean=clean)
