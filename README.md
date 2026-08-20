# Agix

> 本地优先的 AI 个人助理 —— 多模型对话 + 智能任务规划 + 后台定时执行，安全可控。

Agix 是一款跨平台桌面应用，把「日常对话」和「任务自动化」合二为一：你可以像聊天一样向它下达需求，它会对需求做智能分类、拆解成可执行步骤，并在后台按计划（含定时 / 周期）执行；执行过程中涉及的危险命令会被权限系统拦截，敏感信息（如 API Key）以 AES-256-GCM 加密后存储在本机。

## ✨ 核心特性

- **多模型自由切换**：内置 DeepSeek、OpenAI、Kimi、MiniMax、阶跃星辰、硅基流动、Groq、通义千问、智谱 GLM 等 10 个供应商，统一走 OpenAI 兼容接口，还支持自定义 `base_url` 接入任意兼容服务。
- **对话即任务**：输入自然语言需求，Planner 自动分类（软件开发 / 数据分析 / 计划任务 / 其他）并拆解子任务，Executor 后台 worker 负责扫描、执行与周期推进，支持「每 N 分钟 / 指定时间点」这类定时任务。
- **安全权限系统**：内置敏感命令黑名单，覆盖 Linux / Windows / macOS / PowerShell 四类共 19 条规则（`rm -rf`、`sudo`、`dd`、`format`、`Remove-Item -Recurse -Force` 等），命中即拦截，交互模式下弹窗二次确认。
- **本地加密存储**：API Key 等敏感配置用 AES-256-GCM 认证加密，密钥由本机磁盘序列号经 SHA-256 派生，换机无法解密。
- **丰富的工具调用**：文件读写、Shell 执行、`file_patch` 精确改代码、任务管理、计划更新、用户交互等，Agent 可完整落地「写代码 → 跑测试 → 交付」闭环。
- **可扩展生态**：支持技能（Skill）系统与 MCP 服务（高德地图、Bing 搜索等），并管理 SSH 站点，能力可按需接入。
- **跨平台 + 自动升级**：Windows / macOS / Linux 三端桌面应用，GitHub Actions 一键多平台构建，客户端支持版本检测与在线升级。

## 🧰 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Flet 0.85（桌面 UI，多面板） |
| 后端 | Python 3.12 |
| 打包 | PyInstaller 6.21 + Cython 3.0（源码保护） |
| 认证服务 | Flask + Gunicorn + SQLite |
| CI/CD | GitHub Actions 多平台矩阵 |

## 🚀 快速开始

### 下载安装

从发布页下载对应平台的可执行文件（`agix-{version}-{platform}`）：

```
https://www.agix.cc/agix/
```

### 首次配置

1. 启动应用，登录认证服务（首次需短信验证码 / 账号登录）。
2. 进入「设置 → 模型设置」，选择供应商并填入 API Key。
3. 返回对话页，即可开始使用。

> API Key 仅保存在本机，经 AES-256-GCM 加密，不会上传到认证服务器。

## 🔐 安全设计

### 权限规则引擎（`src/auth.py`）

所有敏感命令在执行前经过规则引擎检查，命中黑名单即拦截：

- Linux / macOS：`rm -rf`、`sudo`、`chmod`、`chown`、`mkfs`、`dd`、`kill -9`、`iptables`、`wget | sh` 等。
- Windows：`del /f`、`format`、`reg`、`diskpart`、`net user`、`shutdown`、`takeown`、`icacls` 等。
- PowerShell：`Remove-Item -Recurse -Force`、`Set-ExecutionPolicy`、`Invoke-Expression`、`Stop-Computer`、`Set-Acl` 等。

交互模式下会弹窗请求用户确认，非交互模式直接拒绝。

### 加密存储（`src/aes_crypto.py`）

API Key 采用 AES-256-GCM 认证加密，密钥由本机磁盘序列号 SHA-256 派生，保证敏感信息不落明文、换机不可解密。

## 🏗️ 项目结构

```
src/                     # 核心源码
├── agent.py             # 配置中枢，初始化各组件
├── chater.py            # Chat 对话管理
├── executor.py          # 后台任务调度（定时/周期）
├── planner.py           # 任务分类 + 规划
├── tools.py             # 工具调用（文件/Shell/任务/计划）
├── auth.py              # 权限规则引擎
├── aes_crypto.py        # AES-256-GCM 加密
├── llm_client.py        # 多供应商 LLM 客户端
├── config.py            # 配置管理（供应商/路径/认证）
├── flet_ui/             # Flet 桌面 UI（对话/任务/设置等面板）
└── version.py           # 唯一版本号来源
server/                  # 认证服务（Flask + SQLite）
inner_space/             # 技能、MCP、SSH 等扩展资源
.github/workflows/       # 多平台构建 + 产物分发
```

## 📦 构建与发布

打 tag（`v*`）或在 Actions 手动触发，即自动完成三平台构建：

```bash
git tag v0.1.4
git push github v0.1.4
```

构建流程：读取 tag 版本号 → PyInstaller 打包裸二进制 → 生成 zip 产物与 SHA256 → 生成 `latest.json` 供客户端检测升级。

## 🧩 扩展能力

- **技能系统**：`skill-creator`（创建技能）、`skill-finder`（搜索技能），可按需扩展 Agent 能力。
- **MCP 服务**：`amap`（高德地图 12 个工具）、`bing-search`（Bing 搜索 + 网页抓取）。
- **SSH 站点**：管理远程主机，Agent 可直接操作远端环境。

## 📄 License

本仓库代码仅供学习与内部使用。
