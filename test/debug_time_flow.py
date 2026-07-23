"""模拟修改执行时间触发自动执行的完整数据流"""
import json
import os
import sys
from datetime import datetime

# 模拟各个节点

# 1. 模拟 reschedule_next_execution 的输出格式 (isoformat)
print("=== 节点1: reschedule_next_execution 输出 ===")
next_time = datetime(2026, 7, 23, 15, 58, 0)
iso_time = next_time.isoformat()
print(f"  isoformat: {iso_time!r}")

# 2. 模拟 CupertinoDatePicker confirm 的输出格式 (strftime)
print("\n=== 节点2: CupertinoDatePicker confirm_datetime 输出 ===")
picker_value = datetime(2026, 7, 24, 16, 5, 0)  # 用户选了明天 16:05
strf_time = picker_value.strftime("%Y-%m-%d %H:%M:%S")
print(f"  strftime:  {strf_time!r}")

# 3. 模拟 update_pending_task 保存后，load 读取
print("\n=== 节点3: 保存后用 fromisoformat 解析 ===")
for lbl, val in [("isoformat", iso_time), ("strftime", strf_time)]:
    try:
        parsed = datetime.fromisoformat(val)
        now = datetime.now()
        reached = now >= parsed
        print(f"  {lbl}: {val!r} → parsed={parsed}, now={now}, reached={reached}")
    except Exception as e:
        print(f"  {lbl}: {val!r} → ERROR: {e}")

# 4. 关键：用户只改日期不改时间
print("\n=== 节点4: CupertinoDatePicker 默认值 = datetime.now() ===")
# 用户打开 picker 时，datetime.now() 是当前时间
# 用户只改了日期（比如改成明天），时间没动
now = datetime.now()
tomorrow_same_time = now.replace(day=now.day + 1)
# 但 CupertinoDatePicker minute_interval=1，秒被截断
picker_out = tomorrow_same_time.replace(second=0, microsecond=0)
strf_out = picker_out.strftime("%Y-%m-%d %H:%M:%S")
print(f"  now={now}")
print(f"  picker输出 (明天同时分): {strf_out!r}")
parsed = datetime.fromisoformat(strf_out)
print(f"  解析后: {parsed}")
print(f"  reached: {datetime.now() >= parsed}")

# 5. 边界情况：如果 period 很短，while 循环跳过逻辑
print("\n=== 节点5: reschedule while 循环边界 ===")
current = datetime(2026, 7, 23, 15, 58, 0)
now = datetime(2026, 7, 23, 16, 5, 0)
delta_secs = 20 * 60  # 20 minutes
import datetime as _dt
delta = _dt.timedelta(seconds=delta_secs)
next_time = current + delta
print(f"  current={current}, period=20m → next_time={next_time}")
while next_time <= now:
    print(f"    {next_time} <= {now} → 跳过")
    next_time += delta
print(f"  最终: {next_time} > {now} ✓")
print(f"  status → PENDING")
print(f"  下次扫描时 reached: {datetime.now() >= next_time} (should be False)")

# 6. 竞态条件: 扫描添加 ready 后用户编辑，执行时不再检查时间
print("\n=== 节点6: 竞态条件分析 ===")
print("  场景: 任务时间 15:58, 当前时间 16:00")
print("  16:00.000 — scan 扫描: PENDING + 时间已达 → 加入 ready")
print("  16:00.001 — 用户编辑保存: 时间改为明天 16:05")
print("  16:00.002 — execute: load 任务 → 时间已是明天 → but 不重检时间 → 直接执行!")
print("  结论: 扫描和执行之间无时间重检，存在 ~1ms 竞态窗口")
print("  但如果用户编辑在前(时间未到)，则不会触发此竞态")
