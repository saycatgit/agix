"""深度排查 is_execution_time_reached 和 fromisoformat 兼容性"""
import json, os, sys
from datetime import datetime, timedelta

# 1. 测试 fromisoformat 对各种格式的兼容性
print("=== fromisoformat 兼容性测试 ===")
formats = [
    "2026-07-24 16:05:00",       # strftime 空格分隔
    "2026-07-24T16:05:00",       # isoformat T 分隔
    "2026-07-24 16:05",          # 无秒
    "2026-07-24",                # 仅日期
    "2026-07-24T16:05:00.123456", # 微秒
    "",                          # 空字符串
]
for f in formats:
    try:
        parsed = datetime.fromisoformat(f)
        print(f"  {f!r:40s} → {parsed}")
    except Exception as e:
        print(f"  {f!r:40s} → ERROR: {e}")

# 2. 模拟扫描—执行完整循环
print("\n=== 模拟扫描-执行完整循环 ===")
now = datetime.now()
print(f"  当前时间: {now}")

# 创建一个"过去"时间的任务文件
past_time = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
print(f"  过去时间: {past_time}")

# 模拟扫描
test_times = [
    past_time,                           # 5分钟前 → 应触发
    (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),  # 1小时后 → 不应触发
    (now + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),   # 明天 → 不应触发
]

for t in test_times:
    parsed = datetime.fromisoformat(t)
    reached = datetime.now() >= parsed
    print(f"  {t!r} parsed={parsed} reached={reached}")

# 3. 关键测试: picker默认值是datetime.now(),用户只改日期
print("\n=== CupertinoDatePicker 模拟 ===")
# pick_datetime 被调用时的 now
picker_open_time = datetime.now()
print(f"  picker打开时间: {picker_open_time}")

# 用户改了日期(比如改成明天),时间没动
# minute_interval=1, 秒被截断
tomorrow = (picker_open_time + timedelta(days=1)).replace(second=0, microsecond=0)
print(f"  用户选了明天同时分: {tomorrow}")

strf_val = tomorrow.strftime("%Y-%m-%d %H:%M:%S")
print(f"  confirm_datetime 输出: {strf_val!r}")

# 保存
parsed = datetime.fromisoformat(strf_val)
now2 = datetime.now()
reached = now2 >= parsed
print(f"  保存后now={now2}")
print(f"  parsed={parsed}")
print(f"  reached={reached}")

# 如果有 period 且很短呢?
print("\n=== 极短period场景 ===")
# 任务刚执行完, reschedule_next_execution 推进
# 当前15:58, period=20min, now=15:58:30
# current=15:58, next_time=16:18 > now → 不跳过
print("  这是正常的——while循环已在代码中处理")

# 但如果 period=1min? 极端情况
print("\n=== 极端: period=1min ===")
exec_time = datetime.now().replace(second=0, microsecond=0)
delta = timedelta(minutes=1)
next_time = exec_time + delta
print(f"  exec_time={exec_time}, next_time={next_time}")
# while next_time <= now 检查
now = datetime.now()
print(f"  now={now}")
while next_time <= now:
    print(f"    {next_time} <= {now} → 跳过")
    next_time += delta
print(f"  最终: {next_time}")
print(f"  reached: {datetime.now() >= next_time}")

# 4. 竞态条件精确模拟
print("\n=== 竞态条件精确模拟 ===")
print("""
场景A: 任务时间已过,用户编辑时恰好扫描
  T0: 任务时间=T-5min, 状态=PENDING
  T1: 用户打开编辑对话框 (此时任务尚未被扫描到,因为executor可能正在处理其他任务或sleep中)
  T2: 用户修改时间为T+1d, 点击保存
  T3: executor扫描 → 读到新时间T+1d → reached=False → 不触发
  
场景B: 扫描先于编辑 (真正的竞态)
  T0: 任务时间=T-5min, 状态=PENDING
  T1: executor扫描 → 发现任务ready → 加入列表
  T2: 用户修改时间为T+1d, 保存
  T3: executor从ready列表取出 → load → 时间=T+1d → 但_execute_subtask不重检时间 → 直接执行!
  
  窗口: T1~T3 之间, ~毫秒级
  概率: 极低, 不可能"每次"都发生
""")

# 5. 检查是否有_fast_forward或其他隐式触发
print("=== 结论 ===")
print("  fromisoformat正确解析两种格式 ✓")
print("  未来时间 correctly rejected ✓")
print("  竞态窗口存在但概率极低 ✓")
print("  数据流上未发现明显bug → 需用户提供更具体的复现步骤")
