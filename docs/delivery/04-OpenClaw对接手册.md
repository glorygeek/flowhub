# FlowHub OpenClaw 对接手册

版本：`v0.1.0`  
更新时间：`2026-03-15`

## 1. 对接目标

本手册用于把 FlowHub 接入 OpenClaw 的对话体系。

接入目标是：

- 用户只在 OpenClaw 聊天窗口中操作
- OpenClaw agent 调用 FlowHub 插件工具
- FlowHub 返回工作流方案和确认结果
- 结果继续回到同一聊天线程

## 2. 当前对接方式

当前采用 OpenClaw 本地插件方式，而不是网页跳转方式。

插件目录：

- `openclaw-plugin/`

插件 ID：

- `flowhub-openclaw`

## 3. 插件组成

### 3.1 `openclaw.plugin.json`

作用：

- 声明插件基本信息
- 声明可配置项
- 指定客户侧默认主 Skill 目录

### 3.2 `index.js`

作用：

- 注册工具
- 调用 FlowHub 后端 API
- 把结果格式化为聊天可读文本

### 3.3 `skills/flowhub-orchestrator/SKILL.md`

作用：

- 告诉 OpenClaw agent 在什么场景下使用 FlowHub
- 约束确认逻辑和对话行为

### 3.4 `skills/flowhub-skill-discovery/SKILL.md`

作用：

- 处理“找相关 Skill / 比较候选 Skill”这类发现型问题
- 只做可信 Skill 推荐，不直接触发远程安装
- 当前保留在 Skill 库中，但不再作为客户侧默认主 Skill 挂入插件 manifest

### 3.5 `skills/flowhub-self-improvement/SKILL.md`

作用：

- 仅供内部维护会话记录脱敏后的经验和故障笔记
- 不建议挂入面向外部用户的 FlowHub agent
- 现在可通过单独内部插件包接入：`openclaw-plugin/internal-maintenance/`

## 4. 提供的工具

当前口径：

- `flowhub_handle_message` 是客户侧默认单入口
- 其他工具主要保留为回退入口或调试入口

### 4.1 `flowhub_handle_message`

用途：

- 处理首次访问介绍、安装说明、普通业务请求、补充上下文、确认执行
- 这是客户侧默认优先工具

输入：

- `message`
- `request_id`
- `targets`
- `credentials`
- `output_format`
- `execution_mode`
- `user_notes`

行为：

- 首访/介绍类消息时，直接返回项目简介、功能说明、相关插件/Skill 清单和安装引导
- 普通业务请求时，路由到 `POST /api/v1/run-requests/`
- 明确确认且带真实 `request_id` 时，路由到 `POST /api/v1/run-requests/{id}/confirm`
- 对客户侧来说，它应当是默认入口；只有在路由不可用时才退回显式计划/确认工具

### 4.2 `flowhub_search_skills`

用途：

- 在用户仅想“找 Skill / 比较候选 Skill”时调用

输入：

- `query`
- `category`
- `limit`

行为：

- 请求 `GET /api/v1/skills/search`
- 返回高可信候选 Skill 列表，包含：
  - quality_tier
  - trust_signals
  - source_url
  - ranking_reasons

### 4.3 `flowhub_plan_command`

用途：

- 当 `flowhub_handle_message` 不可用或路由失败时，作为回退规划工具调用

输入：

- `goal`
- `targets`
- `credentials`
- `output_format`
- `execution_mode`
- `user_notes`

行为：

- 请求 `POST /api/v1/run-requests/`
- 获取 workflow 方案
- 返回聊天文本，包含：
  - request_id
  - workflow_id
  - headline
  - reply_text
  - selected_skills
  - usage_steps
  - confirmation_prompt

### 4.4 `flowhub_confirm_request`

用途：

- 当 `flowhub_handle_message` 不可用或路由失败时，作为回退确认工具调用

输入：

- `request_id`

行为：

- 请求 `POST /api/v1/run-requests/{id}/confirm`
- 返回确认后聊天文本，包含：
  - request_id
  - request_status
  - communication_status
  - customer_reply
  - client_execution_guidance
  - client_install_guidance

## 5. 对话规则

OpenClaw agent 应遵循以下规则：

1. 优先在聊天中补齐必要上下文。
2. 首访、介绍、安装、规划、确认都优先调用 `flowhub_handle_message`。
3. 只有在单入口路由不可用时，才调用 `flowhub_plan_command` 或 `flowhub_confirm_request`。
4. 把返回的 workflow 方案和 Skill 说明回复给用户。
5. 必须等待用户明确确认。
6. 不自动代替用户确认。
7. 不在聊天中回显凭据原文。
8. FlowHub 只返回安装指导，不代替任意 OpenClaw 客户端执行本地安装。
9. 只有当用户明确提出“下载 / 安装”时，才由当前 OpenClaw 客户端按本地配置自行处理。

## 6. 插件安装

```bash
openclaw plugins install ./openclaw-plugin
```

内部维护插件安装：

```bash
openclaw plugins install ./openclaw-plugin/internal-maintenance
```

## 7. 插件配置

必须配置：

- `apiBaseUrl`
- `apiKey`

可选配置：

- `timeoutMs`
- `defaultExecutionMode`
- `defaultOutputFormat`

示例：

```json5
{
  "plugins": {
    "allow": ["flowhub-openclaw"],
    "entries": {
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
  }
}
```

说明：

- 当前 OpenClaw CLI 版本下，建议显式配置 `plugins.allow`，避免未信任插件自动加载告警。
- 若只做隔离联调，可使用独立 profile，例如：`openclaw --profile flowhub-test plugins install ./openclaw-plugin`
- 可直接复用模板：
  - [openclaw.local.sample.jsonc](/mnt/f/tool/FlowHub/openclaw-plugin/examples/openclaw.local.sample.jsonc)
  - [openclaw.vps.sample.jsonc](/mnt/f/tool/FlowHub/openclaw-plugin/examples/openclaw.vps.sample.jsonc)

### 7.1 Gateway 最小推荐配置

建议至少显式写出：

```json5
{
  "gateway": {
    "mode": "local",
    "bind": "loopback",
    "port": 18789
  }
}
```

如果默认端口被占用，可切换到其他本地端口，例如 `19089`。

## 8. Agent 绑定建议

建议单独为 FlowHub 创建一个 agent。

原因：

- 便于把 FlowHub 能力与其他 Agent 隔离
- 便于单独配置工具权限
- 便于后续加业务 persona 或专属规则

建议配置思路：

- 单独 agent：`flowhub`
- 允许工具：`flowhub-openclaw`
- 将指定聊天通道绑定到该 agent

内部维护建议：

- 单独 agent：`flowhub-maintenance`
- 只加载 `flowhub-openclaw-internal`
- 不绑定外部用户聊天通道，只供运维或开发人员使用

## 9. 典型对话链路

### 用户回合

```text
用户：帮我抓取 incident API 最新状态，并生成发给客户的 markdown 简报
```

### Agent 内部动作

```text
call flowhub_plan_command
```

### Agent 回复用户

```text
已为你生成 2 个 Skill 的工作流方案：
1. Incident Fetcher
2. Status Summarizer

请确认是否继续执行。
```

### 用户确认

```text
确认
```

### Agent 内部动作

```text
call flowhub_confirm_request
```

### Agent 最终回复

```text
已收到命令，工作流已进入已确认状态。
如需本地下载或安装，请在当前 OpenClaw 客户端明确发送下载/安装指令后继续。
```

### 用户明确提出安装时的回复示例

```text
方案已确认（Request ID: 5）。
当前会话已经明确提出安装/下载意图。请由当前 OpenClaw 客户端按本地配置自行安装所需 Skill。

客户端安装方式：
1. 通用命令：clawhub install us-stock-analysis
   Windows 命令：clawhub.cmd install us-stock-analysis
   Skill 地址：https://clawhub.ai/api/v1/skills/us-stock-analysis

安装完成后，再由当前客户端按本地环境继续执行，不由 FlowHub 服务端代装。
```

## 10. 与 FlowHub 后端的接口关系

OpenClaw 插件不直接操作数据库，也不直接决定 workflow 结构。

它只调用两类接口：

- `POST /api/v1/run-requests/`
- `POST /api/v1/run-requests/{id}/confirm`

FlowHub Backend 负责：

- Skill 检索
- 工作流组合
- 消息内容生成
- 状态推进
- 客户端安装指导生成

OpenClaw 客户端负责：

- 按用户明确指令执行本地插件/Skill 安装
- 按本地环境决定是否继续执行

## 11. 联调建议

联调顺序建议如下：

1. 确认后端 `/health` 正常。
2. 确认 `skills` 表已有同步数据。
3. 通过 curl 或 Postman 验证 `run-requests` 接口。
4. 安装 OpenClaw 插件。
5. 配置 agent 和通道绑定。
6. 用真实聊天消息跑一次 `plan -> confirm`。

## 12. 常见问题

### 12.1 插件调用超时

大概率是 `apiBaseUrl` 不可达，或存在宿主环境网络隔离问题。

### 12.2 用户说“确认”后没有推进

检查：

- agent 是否真的调用了 `flowhub_confirm_request`
- request_id 是否正确

### 12.3 用户对话里看不到 Skill 说明

检查：

- 插件返回文本是否被 agent 正确转述
- FlowHub 是否返回了 `selected_skills`

## 13. WSL / Windows 网络说明

如果后端运行在 WSL，而 OpenClaw 运行在 Windows，本地地址可能需要改为 WSL IP：

```text
http://172.22.xx.xx:8000/api/v1
```

## 14. 对接结论

当前版本已经具备 OpenClaw 对话式接入所需的最小闭环：

- 聊天命令进入 FlowHub
- FlowHub 返回 workflow 方案
- 用户确认后进入待执行状态

后续如果要继续扩展，可以增加：

- 更多领域 Skill
- 更复杂的确认逻辑
- 多轮补充信息流程
