"""任务调度器：管理待执行任务列表，通过 threading.Timer 实现定时执行"""

import os
import json
import threading
from datetime import datetime, timedelta
from typing import Optional


class TaskScheduler:
    """管理 pending_tasks.json，维护一个定时器在最近到期时间触发执行"""

    def __init__(self, pending_file: str, agent):
        self.pending_file = pending_file
        self.agent = agent
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._ready_queue: list = []
        self._stopped = threading.Event()

    # ── 公共 API ──────────────────────────────────────────────

    def add_task(self, task_name: str, first_time_str: str, is_interactive: bool = False,
                 mode: str = "task",
                 is_periodic: bool = False, period: str = "") -> dict:
        """添加定时任务并重新调度定时器。

        first_time_str: ISO 格式时间字符串，或 "now"/"+10m" 等相对时间
        period: 周期字符串，如 "1d", "2h", "30m", "1w"
        """
        next_time = self._parse_time(first_time_str)
        if next_time is None:
            return {"ok": False, "error": f"无法解析时间: {first_time_str}"}

        # 去重：已存在同名未执行任务时跳过
        with self._lock:
            existing = self._load()
            for t in existing:
                if t.get("task_name") == task_name:
                    return {"ok": False, "error": f"任务已存在（同名）: {task_name[:50]}"}

        task = {
            "id": self._next_id(),
            "task_name": task_name,
            "mode": mode,
            "is_periodic": is_periodic,
            "period": period,
            "next_execution_time": next_time.isoformat(),
            "created_at": datetime.now().isoformat(),
            "is_interactive": is_interactive,
        }

        with self._lock:
            tasks = self._load()
            tasks.append(task)
            self._save(tasks)
            self._reschedule(tasks)

        return {"ok": True, "task": task}

    def start(self):
        """启动调度器：扫描已有任务并设定定时器"""
        with self._lock:
            tasks = self._load()
            self._reschedule(tasks)

    def stop(self):
        """停止调度器，取消定时器"""
        self._stopped.set()
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def list_tasks(self) -> list:
        """返回当前 pending 任务列表"""
        return self._load()

    # ── 内部 ──────────────────────────────────────────────────


    def pop_ready_tasks(self) -> list:
        """工作线程调用：取出所有到期待执行的任务"""
        with self._lock:
            tasks = list(self._ready_queue)
            self._ready_queue.clear()
        return tasks

    def _load(self) -> list:
        if not os.path.exists(self.pending_file):
            return []
        try:
            with open(self.pending_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save(self, tasks: list):
        os.makedirs(os.path.dirname(self.pending_file), exist_ok=True)
        with open(self.pending_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)

    def _next_id(self) -> str:
        tasks = self._load()
        max_id = 0
        for t in tasks:
            try:
                n = int(t["id"])
                if n > max_id:
                    max_id = n
            except (ValueError, KeyError):
                pass
        return str(max_id + 1)

    def _parse_time(self, s: str) -> Optional[datetime]:
        if not s or s.strip().lower() in ("now", "immediate", "立即"):
            return datetime.now()
        s = s.strip()
        if s.startswith("+"):
            return datetime.now() + self._parse_duration(s[1:])
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                     "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    def _parse_duration(self, s: str) -> timedelta:
        """解析 "30m", "2h", "1d", "1w" 等"""
        s = s.strip().lower()
        if s.endswith("m"):
            return timedelta(minutes=int(s[:-1]))
        if s.endswith("h"):
            return timedelta(hours=int(s[:-1]))
        if s.endswith("d"):
            return timedelta(days=int(s[:-1]))
        if s.endswith("w"):
            return timedelta(weeks=int(s[:-1]))
        return timedelta(seconds=int(s))

    def _reschedule(self, tasks: list):
        """取消当前定时器，找到最近到期任务并设定新定时器"""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._stopped.is_set() or not tasks:
            return

        now = datetime.now()
        nearest = None
        for t in tasks:
            try:
                dt = datetime.fromisoformat(t["next_execution_time"])
            except (ValueError, KeyError):
                continue
            if nearest is None or dt < nearest:
                nearest = dt

        if nearest is None:
            return

        delay = (nearest - now).total_seconds()
        if delay < 0:
            delay = 1

        self._timer = threading.Timer(delay, self._on_timer)
        self._timer.daemon = True
        self._timer.start()

    def _on_timer(self):
        """定时器回调：扫描到期任务，推入队列，工作线程负责执行"""
        if self._stopped.is_set():
            return

        with self._lock:
            tasks = self._load()
            now = datetime.now()
            remaining = []

            for t in tasks:
                try:
                    dt = datetime.fromisoformat(t["next_execution_time"])
                except (ValueError, KeyError):
                    continue
                if dt <= now:
                    self._ready_queue.append(dict(t))
                else:
                    remaining.append(t)

            # 处理周期任务：计算下次时间，保留在列表中
            for t in tasks:
                if t.get("is_periodic") and t.get("period"):
                    try:
                        dt = datetime.fromisoformat(t["next_execution_time"])
                    except (ValueError, KeyError):
                        continue
                    if dt <= now:
                        delta = self._parse_duration(t["period"])
                        if delta:
                            next_time = dt + delta
                            while next_time <= now:
                                next_time += delta
                            t["next_execution_time"] = next_time.isoformat()
                            remaining.append(t)
                    else:
                        if t not in remaining:
                            remaining.append(t)
                else:
                    # 非周期且未到期的任务保留
                    try:
                        dt = datetime.fromisoformat(t["next_execution_time"])
                        if dt > now and t not in remaining:
                            remaining.append(t)
                    except (ValueError, KeyError):
                        continue

            self._save(remaining)
            self._reschedule(remaining)

