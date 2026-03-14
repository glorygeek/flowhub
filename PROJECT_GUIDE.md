# FlowHub 项目说明

## 1. 项目用途

FlowHub 是一个面向 OpenClaw 生态的自然语言自动化编排平台。

它的目标不是让用户自己挑选 Skill、自己拖工作流，而是让用户直接在 OpenClaw 的对话窗口里发送一句命令，然后由平台完成以下动作：

- 理解用户意图
- 从本地 Skill 索引目录中检索候选 Skill
- 组合成可执行的工作流
- 生成用户可读的回复内容
- 在用户确认后进入待执行状态
- 后续由执行端或客户端运行工作流，并回传 telemetry

当前项目已经实现了以下核心能力：

- ClawHub 公共 Skill 目录同步到本地 `skills` 表
- 基于索引目录的 Skill 检索与工作流组合
- 自然语言命令转工作流方案
- 用户确认前后的对话式回复载荷
- OpenClaw 对话插件桥接
- 客户端运行工作流并上报 telemetry

## 2. 产品定位

FlowHub 在整体系统中的角色是“自动化规划与编排后端”。

用户真正接触的是 OpenClaw 的聊天窗口，不是 FlowHub 的内部管理页面。系统职责分工如下：

- OpenClaw
  - 接收用户消息
  - 维持聊天上下文和会话
  - 调用 FlowHub 插件工具
  - 把 FlowHub 返回内容继续发回同一对话线程
- FlowHub
  - 管理 Skill 索引
  - 解析用户命令
  - 组合工作流
  - 生成确认前后的用户回复内容
  - 提供执行前的结构化数据和接口
- Client Runtime
  - 执行工作流
  - 上报运行结果和 telemetry

## 3. 当前工作流链路

### 3.1 对话入口链路

1. 用户在 OpenClaw 对话窗口中发送命令。
2. OpenClaw agent 调用 `flowhub_plan_command`。
3. OpenClaw 插件请求 FlowHub 接口 `POST /api/v1/run-requests/`。
4. FlowHub 解析命令，从 `skills` 索引中检索候选 Skill，并生成 workflow。
5. FlowHub 返回：
   - 工作流摘要
   - 选中的 Skill 列表
   - 每个 Skill 的简介和使用方式
   - 待确认提示
6. OpenClaw 在原对话中把这些内容回复给用户。
7. 用户明确确认后，OpenClaw 调用 `flowhub_confirm_request`。
8. 插件请求 FlowHub 接口 `POST /api/v1/run-requests/{id}/confirm`。
9. FlowHub 返回可直接发送给用户的确认后消息载荷。

### 3.2 执行链路

1. FlowHub 生成并保存 workflow。
2. Client Runtime 读取 workflow spec。
3. Runtime 顺序执行节点。
4. 执行结果通过 `POST /api/v1/telemetry/events` 回传后端。

## 4. 仓库结构

```text
FlowHub/
├── backend/           FastAPI 后端、数据库模型、Planner、Skill 同步
├── frontend/          Next.js 内部管理与调试页面
├── client/            Tauri + TypeScript 工作流执行端
├── openclaw-plugin/   OpenClaw 插件，对话式接入 FlowHub
├── codex-scripts/     模板生成脚本
├── ClawFlow.md        项目策划文档
├── README.md          简版说明
└── PROJECT_GUIDE.md   当前详细说明文档
```

## 5. 技术栈

### 5.1 后端

- Python 3
- FastAPI
- SQLAlchemy 2
- Alembic
- Pydantic 2
- APScheduler
- httpx
- SQLite

依赖定义见 [requirements.txt](/mnt/f/tool/FlowHub/backend/requirements.txt)。

### 5.2 前端

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS

依赖定义见 [package.json](/mnt/f/tool/FlowHub/frontend/package.json)。

### 5.3 客户端执行端

- Tauri 2
- TypeScript
- `tsx`

依赖定义见 [package.json](/mnt/f/tool/FlowHub/client/package.json)。

### 5.4 OpenClaw 接入层

- OpenClaw Plugin Extension
- JavaScript ESM

插件定义见 [package.json](/mnt/f/tool/FlowHub/openclaw-plugin/package.json) 和 [openclaw.plugin.json](/mnt/f/tool/FlowHub/openclaw-plugin/openclaw.plugin.json)。

## 6. 系统架构

```text
OpenClaw Chat
   |
   v
openclaw-plugin
   |  flowhub_plan_command / flowhub_confirm_request
   v
FlowHub Backend API
   |  run-requests / confirm / skills / workflows / telemetry
   v
SQLite + Planner Engine + Skill Index
   |
   +--> ClawHub Sync Scheduler
   |
   +--> Optional AI Model (/chat/completions)
   |
   +--> Client Runtime Execution
```

## 7. 核心模块说明

### 7.1 Skill 索引模块

用途：

- 把 ClawHub 公共 Skill 目录同步到本地
- 为后续 Skill 检索和工作流规划提供索引数据

关键实现：

- 同步服务：`backend/app/services/clawhub_sync.py`
- 调度器：`backend/app/services/skill_sync_scheduler.py`
- 手动同步接口：`POST /api/v1/skills/sync/clawhub`

### 7.2 Planner 模块

用途：

- 解析用户命令
- 检索本地 Skill 索引
- 组合工作流
- 生成用户可读回复内容

关键实现：

- 主规划器：`backend/app/services/planner_engine.py`
- 可选 AI 规划器：`backend/app/services/planner_ai.py`

当前规划策略：

- 优先从本地 `skills` 索引中挑选候选 Skill
- 本地规则会优先组合“采集型 Skill + 输出型 Skill”
- 如果配置了 AI 模型，则先把候选 Skill 交给模型做进一步选择
- 如果没有候选 Skill，则回退到通用 fallback workflow

### 7.3 Run Request 模块

用途：

- 把一条自然语言命令转成待确认工作流
- 保存 request 和 workflow
- 返回对话式回复内容

关键实现：

- `POST /api/v1/run-requests/`
- `POST /api/v1/run-requests/{id}/confirm`

### 7.4 OpenClaw 插件模块

用途：

- 在 OpenClaw 聊天回合中调用 FlowHub
- 不让用户跳出聊天窗口

关键工具：

- `flowhub_plan_command`
- `flowhub_confirm_request`

关键文件：

- [index.js](/mnt/f/tool/FlowHub/openclaw-plugin/index.js)
- [SKILL.md](/mnt/f/tool/FlowHub/openclaw-plugin/skills/flowhub-orchestrator/SKILL.md)

### 7.5 Client Runtime 模块

用途：

- 在本地或运行端执行 workflow spec
- 回传节点结果和统计信息

关键命令：

```bash
cd client
npm run run-workflow -- --spec ./sample-workflow.json
```

## 8. 对外接口

### 8.1 后端基础地址

默认后端地址：

```text
http://localhost:8000
```

API 前缀：

```text
/api/v1
```

完整基础地址：

```text
http://localhost:8000/api/v1
```

### 8.2 认证方式

所有 API 默认通过请求头认证：

```text
X-API-Key: <FLOWHUB_API_KEY>
```

默认开发值：

```text
dev-flowhub-key
```

### 8.3 主要接口

#### 健康检查

- `GET /`
- `GET /health`

#### Skill 相关

- `GET /api/v1/skills/`
- `POST /api/v1/skills/`
- `POST /api/v1/skills/sync/clawhub`
- `GET /api/v1/skills/{id}`
- `PUT /api/v1/skills/{id}`
- `DELETE /api/v1/skills/{id}`

#### Recipe 相关

- `GET /api/v1/recipes/`
- `POST /api/v1/recipes/`
- `GET /api/v1/recipes/{id}`
- `PUT /api/v1/recipes/{id}`
- `DELETE /api/v1/recipes/{id}`

#### Workflow 相关

- `GET /api/v1/workflows/`
- `POST /api/v1/workflows/`
- `GET /api/v1/workflows/{id}`
- `PUT /api/v1/workflows/{id}`
- `DELETE /api/v1/workflows/{id}`

#### Planner 相关

- `POST /api/v1/planner/plan`

#### 对话命令相关

- `POST /api/v1/run-requests/`
- `GET /api/v1/run-requests/`
- `POST /api/v1/run-requests/{id}/confirm`

#### Telemetry

- `POST /api/v1/telemetry/events`
- `GET /api/v1/telemetry/events`

## 9. AI 接入说明

### 9.1 当前 AI 接入模式

AI 不是直接暴露给前端页面调用，而是作为 Planner 的可选后端能力。

调用路径：

```text
FlowHub Planner -> planner_ai.py -> 外部模型 API
```

### 9.2 AI 接入端口 / 接口

当前实现的外部 AI 接口地址由环境变量控制：

- `PLANNER_AI_BASE_URL`
- `PLANNER_AI_MODEL`
- `PLANNER_AI_API_KEY`

默认值：

```text
PLANNER_AI_BASE_URL=https://api.openai.com/v1
```

当前代码实际请求的接口路径是：

```text
POST {PLANNER_AI_BASE_URL}/chat/completions
```

也就是说，如果使用默认 OpenAI 兼容接口，则实际请求端点为：

```text
POST https://api.openai.com/v1/chat/completions
```

### 9.3 AI 相关环境变量

```env
PLANNER_AI_ENABLED=false
PLANNER_AI_BASE_URL=https://api.openai.com/v1
PLANNER_AI_MODEL=
PLANNER_AI_API_KEY=
PLANNER_AI_TIMEOUT_SECONDS=30
PLANNER_AI_MAX_CANDIDATES=8
```

### 9.4 AI 的作用

当 `PLANNER_AI_ENABLED=true` 且模型配置完整时，Planner 会：

- 把用户命令和目标信息整理成任务描述
- 从本地索引中取出候选 Skill
- 把候选 Skill 列表发给模型
- 让模型返回：
  - 工作流名称
  - 工作流摘要
  - 选中的 Skill slug
  - 每个 Skill 的选择原因
  - 使用步骤
  - 工作流步骤顺序

如果未开启 AI 或 AI 请求失败，则系统自动回退到本地规则规划，不会中断主流程。

## 10. OpenClaw 接入说明

### 10.1 接入方式

当前项目不是让 OpenClaw 跳转网页，而是通过插件方式嵌入对话链路。

插件目录：

- [openclaw-plugin/](/mnt/f/tool/FlowHub/openclaw-plugin)

### 10.2 插件提供的工具

#### `flowhub_plan_command`

用途：

- 接收聊天中的自然语言命令
- 向 FlowHub 创建 run request
- 返回工作流摘要、Skill 列表、使用方式、确认提示

#### `flowhub_confirm_request`

用途：

- 在用户确认后推进 request 状态
- 返回可直接发送给用户的确认后回复内容

### 10.3 插件配置参数

插件配置文件定义见 [openclaw.plugin.json](/mnt/f/tool/FlowHub/openclaw-plugin/openclaw.plugin.json)。

关键配置项：

- `apiBaseUrl`
- `apiKey`
- `timeoutMs`
- `defaultExecutionMode`
- `defaultOutputFormat`

### 10.4 OpenClaw 插件安装

```bash
openclaw plugins install ./openclaw-plugin
```

### 10.5 OpenClaw 典型配置

见 [openclaw-plugin/README.md](/mnt/f/tool/FlowHub/openclaw-plugin/README.md)。

其核心思路是：

- 给 FlowHub 分配一个单独 agent
- 允许该 agent 调用 FlowHub 插件工具
- 把指定聊天通道绑定到这个 agent

## 11. 使用方法

### 11.1 后端启动

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认端口：

```text
8000
```

### 11.2 前端启动

```bash
cd frontend
npm install
npm run dev
```

默认端口：

```text
3000
```

### 11.3 客户端运行

```bash
cd client
npm install
npm run run-workflow -- --spec ./sample-workflow.json
```

### 11.4 首次同步 Skill 索引

```bash
cd backend
python scripts/sync_clawhub_skills.py
```

### 11.5 定时同步 Skill 索引

通过 APScheduler 根据以下配置执行：

```env
CLAWHUB_SYNC_ENABLED=true
CLAWHUB_SYNC_CRON=0 3 * * *
CLAWHUB_SYNC_TIMEZONE=Asia/Shanghai
```

### 11.6 通过 API 创建一条命令规划

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-flowhub-key" \
  http://localhost:8000/api/v1/run-requests/ \
  -d '{
    "goal": "抓取 incident API 的最新状态并输出 markdown 简报",
    "targets": [{"type": "api", "label": "Incident API", "value": "https://example.com/api/incidents/latest"}],
    "credentials": [],
    "output_format": "markdown",
    "execution_mode": "remote",
    "user_notes": "面向客户沟通"
  }'
```

### 11.7 确认一条已生成方案

```bash
curl -X POST \
  -H "X-API-Key: dev-flowhub-key" \
  http://localhost:8000/api/v1/run-requests/1/confirm
```

## 12. 环境变量

完整示例见：

- [.env.example](/mnt/f/tool/FlowHub/.env.example)
- [backend/.env.example](/mnt/f/tool/FlowHub/backend/.env.example)

关键变量如下：

### 12.1 后端基础配置

```env
DATABASE_URL=sqlite:///./data/flowhub.db
FLOWHUB_API_KEY=dev-flowhub-key
```

### 12.2 ClawHub 同步配置

```env
CLAWHUB_REGISTRY_URL=https://clawhub.ai
CLAWHUB_SYNC_ENABLED=true
CLAWHUB_SYNC_ON_STARTUP=false
CLAWHUB_SYNC_CRON=0 3 * * *
CLAWHUB_SYNC_TIMEZONE=Asia/Shanghai
CLAWHUB_SYNC_PAGE_SIZE=100
CLAWHUB_SYNC_TIMEOUT_SECONDS=20
CLAWHUB_SYNC_MAX_RETRIES=8
```

### 12.3 AI 配置

```env
PLANNER_AI_ENABLED=false
PLANNER_AI_BASE_URL=https://api.openai.com/v1
PLANNER_AI_MODEL=
PLANNER_AI_API_KEY=
PLANNER_AI_TIMEOUT_SECONDS=30
PLANNER_AI_MAX_CANDIDATES=8
```

### 12.4 前端配置

```env
FLOWHUB_API_BASE_URL=http://127.0.0.1:8000/api/v1
FLOWHUB_API_KEY=dev-flowhub-key
```

## 13. 数据存储

当前默认数据库为 SQLite：

```text
backend/data/flowhub.db
```

主要表：

- `skills`
- `recipes`
- `workflows`
- `run_requests`
- `telemetry_events`
- `alembic_version`

## 14. 安全与权限

### 14.1 API 鉴权

- 所有 `/api/v1/*` 路径需要 `X-API-Key`

### 14.2 凭据处理

- Run Request 中不会保存原始密钥明文展示
- 后端只保存脱敏后的 `credential_descriptors`
- 对话回复中不会回显用户提交的 credential 值

### 14.3 CORS

默认允许：

- `http://localhost:3000`
- `http://127.0.0.1:3000`

## 15. 测试与验证

已验证的关键路径包括：

- 后端 API 测试
- Planner -> Run Request -> Confirm 链路
- 前端构建
- 前端 lint
- OpenClaw 插件工具语法校验
- OpenClaw 插件对 FlowHub 后端的 plan / confirm 联调

常用验证命令：

```bash
cd backend
python3 -m pytest
```

```bash
cd frontend
npm run lint
npm run build
```

```bash
npm exec -- node --check ./openclaw-plugin/index.js
```

## 16. 当前状态与限制

### 16.1 已实现

- Skill 索引同步
- 自然语言命令规划
- 工作流持久化
- 用户确认链路
- OpenClaw 对话插件桥接
- 可选 AI 规划入口

### 16.2 未完全实现

- 真实 AI 模型调用依赖外部密钥和服务
- 大规模生产级执行调度尚未完成
- OpenClaw 实例侧的正式安装与部署需要在目标环境完成
- Client 的安装包签名、灰度分发和正式发布流程仍需在目标环境落实

### 16.3 环境注意事项

如果 FlowHub 后端运行在 WSL，而 OpenClaw 或 Node 运行在 Windows，本机 `127.0.0.1` 可能不可直接互通，此时需要改用 WSL 的局域网地址，例如：

```text
http://172.22.xx.xx:8000/api/v1
```

## 17. 推荐部署顺序

1. 启动 backend
2. 完成 ClawHub Skill 索引首次同步
3. 配置 AI 模型参数（可选）
4. 安装 `openclaw-plugin`
5. 在 OpenClaw 中创建或绑定 FlowHub agent
6. 把聊天通道绑定到 FlowHub agent
7. 用一条真实聊天命令完成 `plan -> confirm` 联调

## 18. 关键文件索引

- 后端入口：[main.py](/mnt/f/tool/FlowHub/backend/app/main.py)
- 配置中心：[config.py](/mnt/f/tool/FlowHub/backend/app/core/config.py)
- Planner 主逻辑：[planner_engine.py](/mnt/f/tool/FlowHub/backend/app/services/planner_engine.py)
- AI 规划器：[planner_ai.py](/mnt/f/tool/FlowHub/backend/app/services/planner_ai.py)
- Run Request API：[run_requests.py](/mnt/f/tool/FlowHub/backend/app/api/run_requests.py)
- OpenClaw 插件入口：[index.js](/mnt/f/tool/FlowHub/openclaw-plugin/index.js)
- OpenClaw 插件说明：[README.md](/mnt/f/tool/FlowHub/openclaw-plugin/README.md)
