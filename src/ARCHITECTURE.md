# src/ 模块架构

## 模块关系

```
agent.py ──中枢──► chater.py      Chat 对话管理
    │              executor.py    后台任务调度
    │              planner.py     任务分类+规划
    │
    ├─► tools.py           9 工具 + update_plan
    ├─► task_manager.py    单子任务状态 + 持久化
    ├─► prompts.py         提示词 (动态分类/规划/评估)
    ├─► stage_progress.py  阶段步骤进度
    ├─► task_attribute_manager.py  spec.json CRUD
    ├─► llm_client.py      LLM 客户端 (多供应商)
    ├─► auth.py            权限规则引擎
    ├─► aes_crypto.py      AES-256-GCM 加密
    ├─► config.py          配置管理
    ├─► logger.py          日志模块
    ├─► event_queue_manager.py  事件队列
    ├─► meta.py            字段常量
    ├─► node.py            子进程执行
    └─► utils.py           工具函数

flet_ui/
├── flet_app.py           Flet 应用入口
├── chat_panel.py         对话面板
├── status_sidebar.py     状态侧边栏
└── task_config_panel.py  任务配置面板
```

## 核心接口速查

### agent.py
```
Agent(config, auth_handler, eqm)
  .chat_llm / .task_llm          LLM 实例
  .chater: Chater                Chat 模式
  .executor: Executor            任务执行器
  .planner: Planner              任务规划器
  .eqm: EventQueueManager        事件队列
  .stage_progress: StageProgress 阶段进度
```

### chater.py
```
Chater(agent, config, logger, eqm)
  .run(user_message) → dict      执行一轮对话
```

### executor.py
```
Executor(agent, task_dir, eqm)
  .start()                       启动后台 worker
  .stop()                        停止 worker
```

### planner.py
```
Planner(config, logger, eqm)
  .classify(user_task, ...) →    分类任务
  .classify_with_history(...) →  历史关联分类
  .run(user_task, ...) →         完整流程 → TaskManager
```

### task_manager.py
```
SubTaskRecord                    单子任务数据类
  .from_orchestrate_item(idx, item) → SubTaskRecord

TaskManager(save_path)
  .subtask → SubTaskRecord | None
  .set_subtask(item)             设置任务
  .set_subtask_status(status)    更新状态
  .is_execution_time_reached()   时间检查
  .reschedule_next_execution()   周期推进
  .save(path) / .save_state()    持久化

静态方法:
  TaskManager.scan_history_tasks(dir) → [SubTaskRecord]
  TaskManager.list_history_tasks(dir) → [dict]
  TaskManager.list_pending_tasks(dir) → [dict]
```

## 数据持久化

```
inner_space/task/
├── task_{ts}_state.json    任务状态 (subtask + periodic + qa + stage_progress)
└── task_list.json          任务索引 (最近 50 条)

state 文件结构:
{
  "subtask": { SubTaskRecord 字段 },
  "periodic": { is_periodic, period, next_execution_time, ... },
  "global_messages": [ QAMessage ],
  "stage_progress": { StageProgress },
  "periodic_counter": int
}
```
