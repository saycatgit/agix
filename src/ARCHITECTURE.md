# Agent 系统架构文档

## 1. 系统概览

```
┌─────────────────────────────────────────────────────────────────┐
│                   main.py (CLI入口, 344行)                       │
│  交互模式 / 单次执行 / 配置向导 / /llm重新配置                    │
│  AES加密API Key存储 (磁盘序列号加密, 不写rc文件)                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │ agent.run(goal, mode)
┌──────────────────────▼──────────────────────────────────────────┐
│                    agent.py (核心调度)                            │
│  mode="chat": _run_chat()   对话模式                              │
│  mode="task": _run_task()   任务模式 (分类→规划→执行→评估)       │
│  双 LLM: chat_llm / task_llm                                     │
└──────┬──────────────┬──────────────┬───────────────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼──────┐ ┌──────▼──────────┐
│  tools.py   │ │  auth.py  │ │prompts.py  │ │  aes_crypto.py  │
│ 8工具+模糊  │ │ 权限引擎   │ │ 提示词系统  │ │ AES-256-GCM    │
│ 匹配兜底    │ │ 命令检查   │ │ 动态生成    │ │ 磁盘序列号密钥 │
└─────────────┘ └───────────┘ └────────────┘ └─────────────────┘
```

## 2. API Key 存储 (v2 - AES 加密)

```
设置阶段:
  用户输入 sk-xxx → aes_crypto.encrypt(sk-xxx)
  → 输出 'enc:aes:<base64(nonce+ciphertext+tag)>'
  → 存入 config.json (不碰 shell rc 文件)

读取阶段:
  config.json → 'enc:aes:...' 
  → aes_crypto.decrypt()  (磁盘序列号 → SHA-256 → AES密钥)
  → 还原 sk-xxx → 初始化 LLM

安全特性:
  - 密钥绑定本机磁盘序列号 (lsblk → /sys → machine-id → hostname)
  - 拷贝 config.json 到其他机器无法解密
  - 不支持环境变量/rc文件回退 (已删除 _save_env_var/_load_env_from_rc)
```

## 3. 项目文件

```
agent_native/
├── main.py               CLI入口, 配置向导, API Key解析 (AES解密)
├── agent.py              核心调度 (chat/task双模式, 双LLM)
├── llm_client.py         LLM客户端 (OpenAI兼容, 6供应商)
├── tools.py              8工具 + file_patch三级匹配兜底
├── auth.py               权限规则引擎 (敏感命令检查)
├── prompts.py            提示词系统 (动态分类/规划/评估)
├── aes_crypto.py         AES-256-GCM加密 (磁盘序列号绑定)
├── config.py             配置管理 (DEFAULT_CONFIG + 深度合并)
├── logger.py             日志模块 (run_*.log写入)
├── task_manager.py       任务历史扫描/关联
├── task_classifier.py    历史任务分类
├── node.py               子进程任务执行
├── test_sandbox.py       沙箱测试
├── config.json           运行时配置 (含加密API Key)
├── .gitignore            排除 config.json/workspace/log/__pycache__
└── git-server/           本地 bare 仓库
    └── agent_native.git
```

## 4. 认证权限 (auth.py)

```
AuthHandler:
  - sensitive_command_check: 检查rm/sudo/pip/curl|sh等敏感命令
  - interactive: 是否弹交互确认框
  - 三级规则: always_deny → always_ask → always_allow → prompt
  - 持久化: .agent_permissions.json (用户选择缓存)
  - 已移除字段: enabled, sensitive_goal_check (未实现)
```

## 5. 日志系统

```
logger.py:
  - Logger.init(log_dir) → workspace/log/run_{ts}.log
  - llm_client 独立写入 workspace/log/history_{chat,task}.log
  - Agent.__init__ 自动初始化日志 (interactive模式也生效)
```

## 6. 关键变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-29 | API Key 存储改为 AES-256-GCM (磁盘序列号绑定) |
| 2026-06-29 | 删除 _save_env_var / _load_env_from_rc (不再写rc文件) |
| 2026-06-29 | setup_wizard 简化 (去掉环境变量名输入) |
| 2026-06-29 | _resolve_api_key 简化 (仅 enc:aes: + raw sk- 两格式) |
| 2026-06-29 | auth 配置清理 (移除 enabled/sensitive_goal_check) |
| 2026-06-29 | setup_wizard 以 load_config() 为基础继承所有字段 |
| 2026-06-29 | file_patch 增加 _fuzzy_find_context_ws 三级缩进容忍 |
| 2026-06-29 | prompts.py file_patch 描述加强 (前缀列+缩进规则+示例) |
| 2026-06-29 | log.dir 默认值改为空 (走 workspace/log 子目录) |
| 2026-06-29 | Agent.__init__ 增加 Logger 初始化 |
