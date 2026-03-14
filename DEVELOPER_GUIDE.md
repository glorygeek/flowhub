# FlowHub Developer Guide

## 1. 文档定位

本文件面向开发、部署、联调和运维人员。

它重点说明：

- 项目架构
- 模块职责
- 启动方式
- API 和数据流
- OpenClaw 插件接入
- AI 模型接入方式
- 环境变量
- 测试与排障

如果你是产品、运营或客户，需要看更偏业务说明的版本，请使用 [PRODUCT_OVERVIEW.md](/mnt/f/tool/FlowHub/PRODUCT_OVERVIEW.md)。

## 2. 项目目标

FlowHub 是一个面向 OpenClaw 对话入口的自动化规划后端。

目标流程：

1. 用户在 OpenClaw 聊天窗口中发送一句自然语言命令。
2. OpenClaw agent 调用 FlowHub 插件工具。
3. FlowHub 检索本地 Skill 索引并生成工作流方案。
4. 方案通过聊天窗口返回给用户，包括：
   - 工作流摘要
   - 选中的 Skill
   - Skill 简介
   - 使用方式
   - 确认提示
5. 用户确认后，FlowHub 把请求推进到待执行状态。
6. 客户端或执行端按 workflow spec 执行，并上报 telemetry。

## 3. 仓库结构

```text
FlowHub/
├── backend/             FastAPI API、数据库模型、Planner、同步任务
├── frontend/            Next.js 内部页面，用于调试和管理
├── client/              Tauri + TypeScript 工作流执行端
├── openclaw-plugin/     OpenClaw 插件，对话式桥接 FlowHub
├── codex-scripts/       项目模板脚本
├── README.md            简版项目说明
├── PROJECT_GUIDE.md     全量综合文档
├── DEVELOPER_GUIDE.md   当前开发文档
└── PRODUCT_OVERVIEW.md  产品/客户说明文档
```

## 4. 技术栈

### 4.1 Backend

- Python 3
- FastAPI
- SQLAlchemy 2
- Alembic
- Pydantic 2
- APScheduler
- httpx
- SQLite

依赖清单见 [requirements.txt](/mnt/f/tool/FlowHub/backend/requirements.txt)。

### 4.2 Frontend

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS

依赖清单见 [package.json](/mnt/f/tool/FlowHub/frontend/package.json)。

### 4.3 Client Runtime

- Tauri 2
- TypeScript
- `tsx`

依赖清单见 [package.json](/mnt/f/tool/FlowHub/client/package.json)。

### 4.4 OpenClaw Integration

- OpenClaw Plugin Extension
- JavaScript ESM

插件定义见：

- [package.json](/mnt/f/tool/FlowHub/openclaw-plugin/package.json)
- [openclaw.plugin.json](/mnt/f/tool/FlowHub/openclaw-plugin/openclaw.plugin.json)

## 5. 核心架构

```text
User Chat (OpenClaw)
   |
   v
OpenClaw Agent
   |
   v
flowhub-openclaw plugin
   |
   +--> flowhub_plan_command
   +--> flowhub_confirm_request
   |
   v
FlowHub Backend (/api/v1)
   |
   +--> Skill Index (skills)
   +--> Planner Engine
   +--> Run Requests
   +--> Workflows
   +--> Telemetry
   +--> ClawHub Sync Scheduler
   +--> Optional AI Planner
   |
   v
SQLite
```

## 6. 模块职责

### 6.1 Backend

后端入口：

- [main.py](/mnt/f/tool/FlowHub/backend/app/main.py)

职责：

- 提供统一 API
- 启动时执行数据库迁移
- 启动 Skill 定时同步任务
- 处理 Run Request、Workflow、Skill、Telemetry

API 路由汇总：

- [router.py](/mnt/f/tool/FlowHub/backend/app/api/router.py)

### 6.2 Planner Engine

主实现：

- [planner_engine.py](/mnt/f/tool/FlowHub/backend/app/services/planner_engine.py)

职责：

- 对自然语言命令做 token 化
- 结合目标地址提取关键词
- 从本地 `skills` 索引中筛选候选 Skill
- 优先组合“采集型 Skill + 输出型 Skill”
- 生成 workflow nodes / edges
- 生成用户可读回复、Skill 推荐和确认提示

### 6.3 AI Planner

实现：

- [planner_ai.py](/mnt/f/tool/FlowHub/backend/app/services/planner_ai.py)

职责：

- 把候选 Skill 列表发送给外部模型
- 请求模型返回：
  - workflow_name
  - summary
  - selected_skill_slugs
  - usage_steps
  - skill_reasons
  - workflow_steps

如果 AI 不可用，Planner 自动回退到本地规则，不阻塞主流程。

### 6.4 Run Request

实现：

- [run_requests.py](/mnt/f/tool/FlowHub/backend/app/api/run_requests.py)

职责：

- 创建自然语言命令对应的 planning request
- 保存 workflow
- 返回待确认消息载荷
- 用户确认后把 request 状态推进到 `queued`

### 6.5 Skill Sync

实现：

- [clawhub_sync.py](/mnt/f/tool/FlowHub/backend/app/services/clawhub_sync.py)
- [skill_sync_scheduler.py](/mnt/f/tool/FlowHub/backend/app/services/skill_sync_scheduler.py)

职责：

- 同步 ClawHub 公共 Skill 目录
- 幂等更新到本地 `skills` 表
- 定时增量更新

### 6.6 OpenClaw Plugin

实现：

- [index.js](/mnt/f/tool/FlowHub/openclaw-plugin/index.js)
- [SKILL.md](/mnt/f/tool/FlowHub/openclaw-plugin/skills/flowhub-orchestrator/SKILL.md)

职责：

- 向 OpenClaw 注册 FlowHub 工具
- 在聊天中调用 FlowHub 的 `plan` 和 `confirm`
- 保持用户始终留在同一聊天线程

### 6.7 Client Runtime

实现：

- [main.ts](/mnt/f/tool/FlowHub/client/src/main.ts)
- [executor.ts](/mnt/f/tool/FlowHub/client/src/runtime/executor.ts)

职责：

- 读取 workflow spec
- 执行节点
- 回传 telemetry

## 7. API 设计

所有 `/api/v1/*` 路径都要求：

```text
X-API-Key: <FLOWHUB_API_KEY>
```

### 7.1 Health

- `GET /`
- `GET /health`

### 7.2 Skills

- `GET /api/v1/skills/`
- `POST /api/v1/skills/`
- `GET /api/v1/skills/{id}`
- `PUT /api/v1/skills/{id}`
- `DELETE /api/v1/skills/{id}`
- `POST /api/v1/skills/sync/clawhub`

### 7.3 Recipes

- `GET /api/v1/recipes/`
- `POST /api/v1/recipes/`
- `GET /api/v1/recipes/{id}`
- `PUT /api/v1/recipes/{id}`
- `DELETE /api/v1/recipes/{id}`

### 7.4 Workflows

- `GET /api/v1/workflows/`
- `POST /api/v1/workflows/`
- `GET /api/v1/workflows/{id}`
- `PUT /api/v1/workflows/{id}`
- `DELETE /api/v1/workflows/{id}`

### 7.5 Planner

- `POST /api/v1/planner/plan`

主要用于直接调试 planner，不是 OpenClaw 对话主入口。

### 7.6 Run Requests

- `POST /api/v1/run-requests/`
- `GET /api/v1/run-requests/`
- `POST /api/v1/run-requests/{id}/confirm`

这是对话式主链路。

### 7.7 Telemetry

- `POST /api/v1/telemetry/events`
- `GET /api/v1/telemetry/events`

## 8. 关键数据流

### 8.1 计划阶段

```text
OpenClaw chat
  -> flowhub_plan_command
  -> POST /api/v1/run-requests/
  -> Planner 检索本地 Skill 索引
  -> 保存 workflow + run_request
  -> 返回 assistant_response / selected_skills / communication_preview
```

### 8.2 确认阶段

```text
User confirms in chat
  -> flowhub_confirm_request
  -> POST /api/v1/run-requests/{id}/confirm
  -> request.status = queued
  -> 返回 ready_to_send 的对话消息
```

### 8.3 执行阶段

```text
Client Runtime
  -> execute workflow
  -> POST /api/v1/telemetry/events
```

## 9. AI 接入说明

### 9.1 AI 接入位置

AI 只接入后端 Planner，不直接暴露给前端页面。

代码入口：

- [planner_ai.py](/mnt/f/tool/FlowHub/backend/app/services/planner_ai.py)

### 9.2 AI 接入端口

当前采用 OpenAI 兼容接口协议。

后端实际调用地址：

```text
POST {PLANNER_AI_BASE_URL}/chat/completions
```

默认配置下，对应为：

```text
POST https://api.openai.com/v1/chat/completions
```

### 9.3 AI 环境变量

```env
PLANNER_AI_ENABLED=false
PLANNER_AI_BASE_URL=https://api.openai.com/v1
PLANNER_AI_MODEL=
PLANNER_AI_API_KEY=
PLANNER_AI_TIMEOUT_SECONDS=30
PLANNER_AI_MAX_CANDIDATES=8
```

### 9.4 AI 返回内容

模型需要返回 JSON，字段包括：

- `workflow_name`
- `summary`
- `selected_skill_slugs`
- `usage_steps`
- `skill_reasons`
- `workflow_steps`

### 9.5 AI 回退策略

当以下任一条件不满足时，系统自动回退本地规则：

- `PLANNER_AI_ENABLED=true`
- `PLANNER_AI_MODEL` 非空
- `PLANNER_AI_API_KEY` 非空
- AI 请求成功
- AI 返回结构可解析

## 10. OpenClaw 插件接入

### 10.1 插件目录

- [openclaw-plugin/](/mnt/f/tool/FlowHub/openclaw-plugin)

### 10.2 工具定义

#### `flowhub_plan_command`

输入：

- `goal`
- `targets`
- `credentials`
- `output_format`
- `execution_mode`
- `user_notes`

输出：

- `request_id`
- `workflow_id`
- `headline`
- `reply_text`
- `selected_skills`
- `usage_steps`
- `confirmation_prompt`

#### `flowhub_confirm_request`

输入：

- `request_id`

输出：

- `request_status`
- `communication_status`
- `customer_reply`

### 10.3 插件安装

```bash
openclaw plugins install ./openclaw-plugin
```

### 10.4 典型插件配置

```json5
{
  "flowhub-openclaw": {
    "enabled": true,
    "config": {
      "apiBaseUrl": "http://127.0.0.1:8000/api/v1",
      "apiKey": "dev-flowhub-key",
      "timeoutMs": 20000,
      "defaultExecutionMode": "remote",
      "defaultOutputFormat": "markdown"
    }
  }
}
```

完整示例见 [openclaw-plugin/README.md](/mnt/f/tool/FlowHub/openclaw-plugin/README.md)。

### 10.5 WSL/Windows 网络注意事项

如果：

- FlowHub 后端运行在 WSL
- OpenClaw / Node 运行在 Windows

则 OpenClaw 插件里的 `apiBaseUrl` 不能用 `127.0.0.1`，需要改成 WSL 的局域网 IP，例如：

```text
http://172.22.xx.xx:8000/api/v1
```

## 11. 环境变量

完整示例见：

- [.env.example](/mnt/f/tool/FlowHub/.env.example)
- [backend/.env.example](/mnt/f/tool/FlowHub/backend/.env.example)

### 11.1 Backend

```env
DATABASE_URL=sqlite:///./data/flowhub.db
FLOWHUB_API_KEY=dev-flowhub-key
```

### 11.2 ClawHub Sync

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

### 11.3 Frontend

```env
FLOWHUB_API_BASE_URL=http://127.0.0.1:8000/api/v1
FLOWHUB_API_KEY=dev-flowhub-key
```

## 12. 本地启动

### 12.1 Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 12.2 Frontend

```bash
cd frontend
npm install
npm run dev
```

### 12.3 Client

```bash
cd client
npm install
npm run run-workflow -- --spec ./sample-workflow.json
```

## 13. Skill 索引同步

### 13.1 手动同步

```bash
cd backend
python scripts/sync_clawhub_skills.py
```

### 13.2 强制全量刷新

```bash
cd backend
python scripts/sync_clawhub_skills.py --full-refresh
```

### 13.3 API 触发

```bash
curl -X POST \
  -H "X-API-Key: dev-flowhub-key" \
  "http://localhost:8000/api/v1/skills/sync/clawhub?full_refresh=true"
```

## 14. 测试与验证

### 14.1 Backend

```bash
cd backend
python3 -m pytest
```

### 14.2 Frontend

```bash
cd frontend
npm run lint
npm run build
```

### 14.3 OpenClaw Plugin

```bash
npm exec -- node --check ./openclaw-plugin/index.js
```

## 15. 数据库

默认数据库文件：

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

## 16. 典型排障

### 16.1 没有 Skill 命中

检查：

- `skills` 表是否已有同步数据
- Skill 是否为 `approved`
- 请求关键词是否足够明确

### 16.2 OpenClaw 插件超时

检查：

- `apiBaseUrl` 是否可从 OpenClaw 运行环境访问
- 是否存在 WSL/Windows 回环地址不通的问题
- 后端是否已启动

### 16.3 AI 不生效

检查：

- `PLANNER_AI_ENABLED=true`
- `PLANNER_AI_MODEL` 是否配置
- `PLANNER_AI_API_KEY` 是否有效
- 外部模型服务是否可达

### 16.4 Telemetry 未关联 workflow

确保 workflow spec 中已带 `workflow_id`，Client Runtime 会优先上报该字段。

## 17. 当前实现边界

已完成：

- 对话式规划
- Skill 索引同步
- 工作流持久化
- 用户确认
- OpenClaw 插件桥接
- 客户端 telemetry 回传
- 可选 AI 规划入口

未完全完成：

- 真实生产级执行调度
- OpenClaw 目标环境正式部署
- AI 模型生产化监控与成本控制
- Client 安装包签名、灰度分发和正式发布流程
