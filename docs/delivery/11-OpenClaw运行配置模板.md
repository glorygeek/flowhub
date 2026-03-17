# OpenClaw 运行配置模板

版本：`v0.1.0`  
更新时间：`2026-03-17`

## 1. 目标

本文件提供两套可直接复用的 OpenClaw 运行模板：

- 本地联调模板
- VPS / 远程 FlowHub 模板

适用场景：

- 新机器快速起一套可测 OpenClaw
- 将 FlowHub 对接到新的 OpenClaw profile
- 排查“网关起不来 / 插件能装但 agent 不通 / FlowHub 不可达”等问题

## 2. 模板文件

模板位置：

- [openclaw.local.sample.jsonc](/mnt/f/tool/FlowHub/openclaw-plugin/examples/openclaw.local.sample.jsonc)
- [openclaw.vps.sample.jsonc](/mnt/f/tool/FlowHub/openclaw-plugin/examples/openclaw.vps.sample.jsonc)
- [flowhub.workspace.AGENTS.sample.md](/mnt/f/tool/FlowHub/openclaw-plugin/examples/flowhub.workspace.AGENTS.sample.md)
- [bootstrap_openclaw_flowhub.py](/mnt/f/tool/FlowHub/openclaw-plugin/scripts/bootstrap_openclaw_flowhub.py)
- [run_openclaw_flowhub_gateway.py](/mnt/f/tool/FlowHub/openclaw-plugin/scripts/run_openclaw_flowhub_gateway.py)
- [run_openclaw_flowhub_smoke.py](/mnt/f/tool/FlowHub/openclaw-plugin/scripts/run_openclaw_flowhub_smoke.py)
- [flowhub_openclaw_admin.py](/mnt/f/tool/FlowHub/openclaw-plugin/scripts/flowhub_openclaw_admin.py)
- [flowhub_openclaw_admin.cmd](/mnt/f/tool/FlowHub/openclaw-plugin/scripts/flowhub_openclaw_admin.cmd)

## 3. 最小必需项

不论本地还是 VPS，至少保证以下字段存在：

```json
{
  "gateway": {
    "mode": "local",
    "bind": "loopback",
    "port": 18789
  },
  "plugins": {
    "allow": ["flowhub-openclaw"],
    "entries": {
      "flowhub-openclaw": {
        "enabled": true,
        "config": {
          "apiBaseUrl": "http://127.0.0.1:8000/api/v1",
          "apiKey": "your-flowhub-api-key"
        }
      }
    }
  }
}
```

说明：

- 推荐创建独立 `agentId=flowhub` 和独立 workspace，例如 `~/.openclaw/workspace-flowhub`
- `gateway.mode=local` 是当前 profile 能否正常启动 gateway 的关键项
- `plugins.allow` 建议显式写出 `flowhub-openclaw`
- `apiBaseUrl` 必须指向 FlowHub 实际可达地址
- `apiKey` 必须与 FlowHub 后端 `X-API-Key` 对应
- 建议把 [flowhub.workspace.AGENTS.sample.md](/mnt/f/tool/FlowHub/openclaw-plugin/examples/flowhub.workspace.AGENTS.sample.md) 复制为该 workspace 的 `AGENTS.md`，把首访介绍、安装指导和业务请求统一收敛到 `flowhub_handle_message`

## 4. 本地联调模板

适合：

- OpenClaw 和 FlowHub 在同一台机器
- 或浏览器 / OpenClaw 在 Windows，FlowHub 后端在 Windows 本机

默认模板：

- [openclaw.local.sample.jsonc](/mnt/f/tool/FlowHub/openclaw-plugin/examples/openclaw.local.sample.jsonc)

推荐使用：

```json
"apiBaseUrl": "http://127.0.0.1:8000/api/v1"
```

如果端口 `18789` 已被占用：

1. 改 `gateway.port`，例如 `19089`
2. 重启 gateway
3. 用新端口执行健康检查

## 5. VPS / 远程 FlowHub 模板

适合：

- OpenClaw 跑在用户本地
- FlowHub 后端部署在 VPS / 云服务器

默认模板：

- [openclaw.vps.sample.jsonc](/mnt/f/tool/FlowHub/openclaw-plugin/examples/openclaw.vps.sample.jsonc)

关键替换：

```json
"apiBaseUrl": "https://your-flowhub-domain.example.com/api/v1"
```

注意：

- FlowHub 必须对 OpenClaw 所在客户端可达
- 如果用 HTTPS，证书必须有效
- 若是反向代理，请确保 `/api/v1` 正常转发到 FlowHub 后端

## 6. 推荐启动顺序

1. 创建独立 FlowHub workspace
2. 把 [flowhub.workspace.AGENTS.sample.md](/mnt/f/tool/FlowHub/openclaw-plugin/examples/flowhub.workspace.AGENTS.sample.md) 复制为该 workspace 的 `AGENTS.md`
3. 启动 FlowHub 后端
4. 验证 `apiBaseUrl` 可达
5. 安装或更新 FlowHub 插件
6. 启动 OpenClaw gateway
7. 执行健康检查
8. 再进行 agent 会话测试

## 7. 推荐命令

### 一键生成 profile + workspace 模板

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py bootstrap \
  --mode local \
  --profile-dir ~/.openclaw-flowhub \
  --workspace-dir ~/.openclaw/workspace-flowhub \
  --api-base-url http://127.0.0.1:8000/api/v1 \
  --api-key your-flowhub-api-key \
  --validate-profile \
  --check-plugins
```

该脚本会：

- 生成 `openclaw.json`
- 复制 FlowHub 专用 `AGENTS.md`
- 生成 `FLOWHUB_BOOTSTRAP_NEXT_STEPS.md`

### 一键生成并安装插件

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py bootstrap \
  --mode local \
  --profile-dir ~/.openclaw-flowhub \
  --workspace-dir ~/.openclaw/workspace-flowhub \
  --api-base-url http://127.0.0.1:8000/api/v1 \
  --api-key your-flowhub-api-key \
  --install-plugin \
  --validate-profile \
  --check-plugins
```

补充说明：

- `--install-plugin` 会在写完 profile 后自动执行 `openclaw --profile <name> plugins install <plugin-path>`
- 如果当前机器需要通过包装命令调用 OpenClaw，可加：

```bash
--openclaw-command "cmd.exe /C openclaw"
```

- 如果只想验证命令拼装，不想真正安装插件，可使用：

```bash
--openclaw-command /bin/echo
```

### 可选后置动作

脚本还支持以下验证或联调动作：

- `--validate-profile`
- `--check-plugins`
- `--start-gateway-service`
- `--gateway-health-check`
- `--smoke-test`
- `--run-gateway-foreground`

示例：

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py bootstrap \
  --mode local \
  --profile-dir ~/.openclaw-flowhub \
  --workspace-dir ~/.openclaw/workspace-flowhub \
  --api-base-url http://127.0.0.1:8000/api/v1 \
  --api-key your-flowhub-api-key \
  --install-plugin \
  --validate-profile \
  --check-plugins \
  --gateway-health-check \
  --smoke-test
```

说明：

- `--start-gateway-service` 依赖目标机器已经安装过 gateway service，且当前用户具备对应权限
- `--gateway-health-check` 和 `--smoke-test` 更适合在 gateway 已经运行时使用
- `--run-gateway-foreground` 会在 bootstrap 结束后直接调用 [run_openclaw_flowhub_gateway.py](/mnt/f/tool/FlowHub/openclaw-plugin/scripts/run_openclaw_flowhub_gateway.py) 进入前台 `gateway run`
- 如果只想预览这条前台命令，可再加 `--run-gateway-print-only`

### 安装插件

```bash
openclaw --profile flowhub-test plugins install ./openclaw-plugin
```

### 校验配置

```bash
openclaw --profile flowhub-test config validate
```

### 前台启动 gateway

```bash
openclaw --profile flowhub-test gateway run --port 18789
```

推荐优先使用辅助脚本，它会自动读取 profile 里的 `gateway.port`、`gateway.bind` 和 token：

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py gateway \
  --profile-dir ~/.openclaw-flowhub
```

如果 OpenClaw 需要通过 Windows `cmd` 调起：

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py gateway \
  --profile-dir /mnt/c/Users/Administrator/.openclaw-flowhub \
  --openclaw-command "cmd.exe /C openclaw"
```

如果 `18789` 有问题：

```bash
openclaw --profile flowhub-test gateway run --port 19089
```

### 检查 gateway

```bash
openclaw --profile flowhub-test gateway health
openclaw --profile flowhub-test health
```

### 发起 agent 测试

```bash
openclaw --profile flowhub-test agent --agent flowhub --to +15550004444 --message "请使用 FlowHub 平台为我规划一个工作流：分析 AAPL 最近三个月走势，并返回 markdown 摘要。" --json
```

推荐优先使用首访 smoke helper：

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py smoke \
  --profile-dir ~/.openclaw-flowhub
```

Windows 用户也可以直接使用 `.cmd` 包装入口：

```bat
openclaw-plugin\scripts\flowhub_openclaw_admin.cmd bootstrap ^
  --mode local ^
  --profile-dir %USERPROFILE%\.openclaw-flowhub ^
  --workspace-dir %USERPROFILE%\.openclaw\workspace-flowhub ^
  --api-base-url http://127.0.0.1:8000/api/v1 ^
  --api-key your-flowhub-api-key ^
  --install-plugin ^
  --validate-profile ^
  --check-plugins
```

## 8. 当前推荐测试口径

建议用两条消息做验收：

### 第零条：首次访问

```text
你好，第一次使用 FlowHub，请先介绍一下项目、主要功能、相关插件和技能清单，并告诉我怎么安装。
```

预期：

- 优先调用 `flowhub_handle_message`
- 返回项目简介
- 返回相关插件 / Skill 清单
- 返回安装前置条件与安装指导
- 不误创建工作流

### 第一条：规划

```text
请使用 FlowHub 平台为我规划一个工作流：分析 AAPL 最近三个月走势，并返回 markdown 摘要。请返回工作流公式、选中的 Skill、确认提示，并说明只有用户明确要求下载或安装时才由客户端自行处理。
```

预期：

- 返回工作流公式
- 返回选中的 Skill
- 返回安全建议
- 明确说明“客户端自管安装”

### 第二条：确认并安装

```text
确认执行，并下载安装所需 Skill。只返回安装指导和命令，不要自行执行任何备用抓取、API 请求、网页搜索或分析。
```

预期：

- 返回安装命令，例如 `clawhub install us-stock-analysis`
- 不自动代装
- 不自动走备用抓取/分析

## 9. 常见故障

### 9.1 gateway 无法启动

优先检查：

- `gateway.mode=local` 是否存在
- `gateway.port` 是否冲突
- 当前 profile 是否真的被使用

### 9.2 gateway health 超时

优先检查：

- 端口监听是否存在
- 是否有旧进程卡住旧端口
- 当前 CLI 是否在连接错误端口

### 9.3 插件能加载但 FlowHub 不可达

优先检查：

- `plugins.entries.flowhub-openclaw.config.apiBaseUrl`
- `apiKey`
- VPS 出口网络 / 反向代理

### 9.4 安装提示正确，但 agent 仍试图代执行

优先检查：

- 是否使用了最新的 `flowhub-orchestrator`
- 当前会话是否仍缓存旧上下文
- 是否在消息里明确要求“只返回安装指导”

## 10. 当前真实经验

当前本地联调中，旧端口 `18789` 曾存在无法以当前权限结束的遗留 node 进程。  
因此在实际排障中，直接切换到新端口 `19089` 并重启 gateway，是更稳的恢复方式。

这说明：

- OpenClaw 不一定需要重装
- 先区分“配置问题 / 端口问题 / 服务权限问题”更重要
- 本地联调阶段可以先用前台 `gateway run`，不必强依赖系统服务
