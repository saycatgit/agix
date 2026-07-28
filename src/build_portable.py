#!/usr/bin/env python3
"""跨平台 portable 打包脚本 — PyInstaller --onefile，支持 Cython 源码保护

用法:
    python build_portable.py              # 普通打包
    python build_portable.py --cython     # Cython 编译 .py → .so/.pyd 后打包
    python build_portable.py --clean      # 清理所有构建缓存

--cython 模式：
    1. 编译 src/*.py → .so(linux/macOS) / .pyd(Windows) 原生二进制
    2. run_flet.py 保留为 .py 入口
    3. 最终产物不含 Python 明文源码

依赖: PyInstaller、Cython（仅 --cython 模式）、C 编译器
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
INNER_SPACE = PROJECT_ROOT / "inner_space"
WORKSPACE = PROJECT_ROOT / "workspace"
RELEASE_DIR = PROJECT_ROOT / "release"
BUILD_DIR = PROJECT_ROOT / ".pyinstaller_build"
CYTHON_BUILD_DIR = PROJECT_ROOT / ".cython_build"

ENTRY_MODULE = "run_flet"

EXCLUDE_MODULES = [
    "torch",
    "tensorflow",
    "transformers",
    "numpy",
    "scipy",
    "pandas",
    "numba",
    "llvmlite",
    "pyarrow",
    "matplotlib",
    "plotly",
    "PIL",
    "lxml",
    "sqlalchemy",
    "twisted",
    "coverage",
    "astroid",
    "pylint",
    "IPython",
    "nbformat",
    "openpyxl",
    "xlrd",
    "xlsxwriter",
    "jupyter_client",
    "notebook",
    "nbconvert",
    "Cython",
    "jedi",
    "pyximport",
    "zstandard",
]

# Cython .so 模式下 PyInstaller 无法追踪任何 Python import 链（遇到 .so 即终止）
# 因此所有被编译模块 + 第三方依赖必须全部显式声明
# 内部模块（21 个，Cython 编译目标）：
INTERNAL_MODULES = [
    "aes_crypto",
    "agent",
    "auth",
    "auth_token",
    "chater",
    "config",
    "event_queue_manager",
    "executor",
    "flet_app",
    "llm_client",
    "logger",
    "meta",
    "node",
    "planner",
    "prompts",
    "stage_progress",
    "task_attribute_manager",
    "task_manager",
    "tools",
    "utils",
]
# flet_ui 子包模块：
FLET_UI_MODULES = [
    "flet_ui.about_panel", "flet_ui.chat_panel", "flet_ui.connection_settings_panel",
    "flet_ui.model_settings_panel", "flet_ui.status_sidebar", "flet_ui.sys_settings_panel",
    "flet_ui.task_config_panel", "flet_ui.task_panel", "flet_ui.unified_settings_panel",
]
# 第三方依赖（.so 中引用，PyInstaller 无法追踪）：
CYTHON_HIDDEN_IMPORTS = [
    "requests",
    "openai",
    "cryptography",
    "cryptography.hazmat.primitives.ciphers.aead",
    # 其他自动检测的第三方依赖由 _collect_deps() 补充
] + INTERNAL_MODULES + FLET_UI_MODULES


def find_pyinstaller() -> Path:
    candidates = []
    if hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix):
        candidates.append(Path(sys.prefix) / "bin" / "pyinstaller")
        if os.name == "nt":
            candidates.append(Path(sys.prefix) / "Scripts" / "pyinstaller.exe")
    which = shutil.which("pyinstaller")
    if which:
        candidates.append(Path(which))
    for p in candidates:
        if p.is_file():
            return p
    print("❌ 找不到 PyInstaller，请先 pip install pyinstaller")
    sys.exit(1)


def check_c_compiler() -> bool:
    """检查是否有可用的 C 编译器"""
    if os.name == "nt":
        return shutil.which("cl.exe") is not None or shutil.which("gcc") is not None
    return shutil.which("cc") is not None or shutil.which("gcc") is not None or shutil.which("clang") is not None


def cython_compile() -> Path:
    """Cython 编译 src/*.py → .so/.pyd，返回编译产物目录"""
    from Cython.Build import cythonize
    import setuptools

    if not check_c_compiler():
        print("❌ --cython 需要 C 编译器（Linux: gcc, macOS: clang, Windows: MSVC/MinGW）")
        sys.exit(1)

    # 清理并重建编译目录
    if CYTHON_BUILD_DIR.exists():
        shutil.rmtree(CYTHON_BUILD_DIR)
    CYTHON_BUILD_DIR.mkdir()

    # 复制 src 到编译目录
    compiled_src = CYTHON_BUILD_DIR / "src"
    shutil.copytree(SRC_DIR, compiled_src)
    print(f"📋 复制源码 → {compiled_src}")

    # 收集要编译的 .py（排除入口文件和 __init__.py）
    py_files = []
    for f in sorted(compiled_src.glob("*.py")):
        if f.stem == ENTRY_MODULE:
            continue
        if f.name == "__init__.py":
            continue
        py_files.append(f)

    if not py_files:
        print("⚠️ 没有找到需要编译的 .py 文件")
        return compiled_src

    print(f"🔧 Cython 编译 {len(py_files)} 个模块...")

    # 逐模块编译，单个失败不影响其他
    compiled_count = 0
    for py_file in py_files:
        try:
            cwd = os.getcwd()
            os.chdir(str(compiled_src))
            ext = cythonize(
                [py_file.name],
                compiler_directives={"language_level": "3"},
                quiet=True if compiled_count > 0 else False,
            )
            setuptools.setup(
                ext_modules=ext,
                script_args=["build_ext", "--inplace"],
            )
            os.chdir(cwd)
            compiled_count += 1
            # 删除 .c 但保留 .py（PyInstaller 需要 .py 追踪依赖，运行时 .so 优先）
            c_file = py_file.with_suffix(".c")
            if c_file.exists():
                c_file.unlink()
        except Exception as e:
            os.chdir(cwd)
            print(f"   ⚠️ {py_file.name} 编译失败: {e}，保留 .py")

    # 清理 setuptools 生成的 build 目录
    build_artifacts = compiled_src / "build"
    if build_artifacts.exists():
        shutil.rmtree(build_artifacts)

    print(f"   ✅ {compiled_count}/{len(py_files)} 个模块编译完成")

    return compiled_src


def _collect_add_data_files(dir_path: Path, dest_prefix: str, separator: str) -> list:
    """遍历目录下所有文件，为每个文件生成 --add-data 参数，保证无一遗漏。

    排除 __pycache__、*.pyc、*.bk 等无关文件。
    返回: ['/abs/path/file:dest_dir', ...]
    """
    if not dir_path.exists():
        return []
    items = []
    for f in dir_path.rglob('*'):
        if not f.is_file():
            continue
        if '__pycache__' in f.parts:
            continue
        if f.suffix in ('.pyc', '.bk'):
            continue
        rel = f.relative_to(dir_path)
        dest = f"{dest_prefix}/{rel.parent}"
        items.append(f"{f}{separator}{dest}")
    return items


def build(clean: bool = False, use_cython: bool = False) -> None:
    pyinstaller = find_pyinstaller()
    separator = ";" if os.name == "nt" else ":"
    exe_suffix = ".exe" if os.name == "nt" else ""

    if clean:
        for d in [BUILD_DIR, RELEASE_DIR, CYTHON_BUILD_DIR]:
            if d.exists():
                print(f"🧹 清理 {d}")
                shutil.rmtree(d)

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    if use_cython:
        src_for_build = cython_compile()
        entry_script = src_for_build / f"{ENTRY_MODULE}.py"
    else:
        src_for_build = SRC_DIR
        entry_script = SRC_DIR / f"{ENTRY_MODULE}.py"

    # --add-data: 文件级别逐个添加，避免 PyInstaller 目录递归遗漏
    add_data_items = _collect_add_data_files(INNER_SPACE, "inner_space", separator)
    add_data_items += _collect_add_data_files(WORKSPACE, "workspace", separator)
    print(f"📋 资源文件: {len(add_data_items)} 个")

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

    # Cython 模式：添加编译目录到搜索路径，PyInstaller 可分析 .py 依赖链
    if use_cython:
        cmd.extend(["--paths", str(src_for_build)])
        for hidden_import in CYTHON_HIDDEN_IMPORTS:
            cmd.extend(["--hidden-import", hidden_import])

    cmd.append(str(entry_script))

    print(f"\n📦 目标平台: {'Windows' if os.name == 'nt' else sys.platform}")
    if use_cython:
        print(f"🔒 源码保护: Cython 编译模式")
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


if __name__ == "__main__":
    clean = "--clean" in sys.argv
    use_cython = "--cython" in sys.argv
    build(clean=clean, use_cython=use_cython)
