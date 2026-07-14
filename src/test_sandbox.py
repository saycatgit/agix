#!/usr/bin/env python3
"""沙箱架构演示

演示内容：
  1. 检测当前是否已在沙箱内
  2. 沙箱进程关系（init → bash → 子命令）
  3. 创建嵌套沙箱并通信
  4. 沙箱生命周期（持久 vs 短命令）

回答两个问题:
  - 沙箱进程组一直是活跃的吗？  → 是，bwrap(PID1) 和 bash(PID2) 常驻
  - 我这算不算在沙箱中建沙箱？    → 算，这是嵌套沙箱演示
"""

import subprocess, os, sys, time, signal


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def run(cmd: str, timeout: int = 10) -> str:
    """运行命令并捕获输出"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout.strip() or r.stderr.strip()
    except subprocess.TimeoutExpired:
        return "(timeout)"


# ================================================================
# Part 1: 检测当前沙箱环境
# ================================================================
section("Part 1: 当前沙箱环境")

# 方法1: PID 1 是 bwrap 吗？
init_exe = os.readlink("/proc/1/exe")
in_sandbox = "bwrap" in init_exe
print(f"  /proc/1/exe → {init_exe}")
print(f"  已在沙箱内: {'是' if in_sandbox else '否'}")

# 方法2: 看 mountinfo 里的 bind mount
mountinfo = run("cat /proc/self/mountinfo | grep '/home/agent' | head -3")
print(f"  挂载信息 (工作区):\n    {mountinfo[:200]}")

# 方法3: PID 空间
my_pid = os.getpid()
print(f"  当前进程 PID (沙箱内): {my_pid}")
print(f"  存在的 PID: {run('ls /proc | grep -E \"^[0-9]+$\" | head -10')}")

# ================================================================
# Part 2: 进程关系 — 沙箱内进程树
# ================================================================
section("Part 2: 沙箱进程关系")

print("  沙箱内进程树:")
print(f"    {run('ps -o pid,ppid,comm --forest 2>/dev/null || ps aux | head -10')}")

print("\n  结构:")
print("    PID 1: bwrap      ← init (常驻)")
print("    PID 2: /bin/bash  ← shell (常驻)")
print("    每次 exec_command: bash fork() 子进程执行命令")

# ================================================================
# Part 3: 演示 — "长生命周期" vs "短命令"
# ================================================================
section("Part 3: 长生命周期进程 vs 短命令")

print("  启动一个长生命周期 bash，用管道通信...")
proc = subprocess.Popen(
    ["bash"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, text=True, bufsize=1
)

def send_cmd(cmd: str) -> str:
    proc.stdin.write(cmd + "\n")
    proc.stdin.write("echo '---END---'\n")
    proc.stdin.flush()
    output = []
    while True:
        line = proc.stdout.readline()
        if not line or '---END---' in line:
            break
        output.append(line.rstrip())
    return "\n".join(output)

print(f"  bash 子进程 PID: {proc.pid}")

r1 = send_cmd("echo '你好，这是一个持久 bash'")
print(f"  命令1 输出: {r1}")

r2 = send_cmd("date '+时间: %H:%M:%S'")
print(f"  命令2 输出: {r2}")

r3 = send_cmd("echo 'PID不变' && echo $$")
print(f"  命令3 (PID未变): {r3}")

proc.stdin.write("exit\n"); proc.stdin.flush()
proc.wait()
print("  持久 bash 已退出")

# ================================================================
# Part 4: 嵌套沙箱 — 在沙箱中创建沙箱
# ================================================================
section("Part 4: 嵌套沙箱 (sandbox-in-sandbox)")

print("  在已有的 bwrap 沙箱内，再启动一个 bwrap 子沙箱...")

# 尝试创建嵌套沙箱
nested = subprocess.run(
    [
        "bwrap",
        "--ro-bind", "/", "/",          # 根只读 (已是只读，再次确认)
        "--bind", "/tmp", "/tmp",       # /tmp 可写
        "--bind", "/home/agent", "/home/agent",  # 工作区可写
        "--unshare-net",                 # 网络隔离 (外层已有，嵌套叠加)
        "--unshare-pid",                 # PID 隔离 (嵌套)
        "--proc", "/proc",
        "--",
        "bash", "-c",
        # 在嵌套沙箱内执行的命令
        'echo "  [嵌套沙箱] PID 1 exe = $(readlink /proc/1/exe)"; '
        'echo "  [嵌套沙箱] 我的 PID = $$"; '
        'echo "  [嵌套沙箱] 网络测试 = $(curl -s --connect-timeout 2 https://example.com 2>&1 || echo "不可达")"; '
        'echo "  [嵌套沙箱] /home/agent 可写测试: $(echo test > /home/agent/_nest_test 2>&1; cat /home/agent/_nest_test 2>/dev/null; rm -f /home/agent/_nest_test)"'
    ],
    capture_output=True, text=True, timeout=15
)

if nested.returncode == 0:
    print("  ✅ 嵌套沙箱创建成功")
    for line in nested.stdout.strip().split("\n"):
        print(f"  {line}")
else:
    print(f"  ⚠ 嵌套沙箱失败 (rc={nested.returncode})")
    print(f"  stderr: {nested.stderr[:300]}")
    print()
    print("  → 尝试不带 --unshare-pid (外层的 seccomp 可能限制了 CLONE_NEWPID)...")
    nested2 = subprocess.run(
        [
            "bwrap",
            "--ro-bind", "/", "/",
            "--bind", "/tmp", "/tmp",
            "--bind", "/home/agent", "/home/agent",
            "--unshare-net",
            # 不加 --unshare-pid
            "--",
            "bash", "-c",
            'echo "  [嵌套沙箱 v2] PID 1 exe = $(readlink /proc/1/exe)"; '
            'echo "  [嵌套沙箱 v2] 我的 PID = $$"; '
            'echo "  [嵌套沙箱 v2] 工作区文件可见: $(ls /home/agent/test_sandbox.py 2>&1)"'
        ],
        capture_output=True, text=True, timeout=15
    )
    if nested2.returncode == 0:
        print("  ✅ 嵌套沙箱 v2 创建成功")
        for line in nested2.stdout.strip().split("\n"):
            print(f"  {line}")
    else:
        print(f"  ❌ 也失败了: {nested2.stderr[:200]}")

# ================================================================
# Part 5: 总结
# ================================================================
section("Part 5: 总结")

print("""
  进程关系:
    Codex CLI (外部宿主)
      └─ [fork/exec] → bwrap (PID 1, init, 常驻)
            └─ [exec] → codex-linux-x64 → bash (PID 2, shell, 常驻)
                  └─ [fork] → python3 test_sandbox.py  (短命令)
                        └─ [fork] → bwrap (嵌套沙箱, 演示用)

  问题回答:
    Q: 沙箱进程组一直是活跃的吗？
    A: 是。bwrap(PID1) 作为 init 和 bash(PID2) 作为 shell 在你整个
       会话期间持续运行。每个 exec_command 只是 bash 内部 fork/exec
       一个子进程，不是重建整个沙箱。

    Q: 我这算不算在沙箱中建沙箱？
    A: 算。你启动 bwrap 时，是在外层 bwrap 创建的命名空间内部再
       创建新的命名空间，形成嵌套隔离。Linux 内核支持这种嵌套
       (user namespace nesting)，每层可以进一步收紧限制。
""")

