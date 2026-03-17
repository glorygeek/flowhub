# OpenClaw 运维速查卡

版本：`v0.1.0`  
更新时间：`2026-03-18`

## 1. 适用范围

本页用于快速完成：

- FlowHub OpenClaw profile 初始化
- 插件安装
- 前台 gateway 启动
- 首访 smoke test
- 常见问题排查

优先使用统一入口：

- [flowhub_openclaw_admin.py](/mnt/f/tool/FlowHub/openclaw-plugin/scripts/flowhub_openclaw_admin.py)
- [flowhub_openclaw_admin.cmd](/mnt/f/tool/FlowHub/openclaw-plugin/scripts/flowhub_openclaw_admin.cmd)

## 2. Linux / WSL 常用命令

### 初始化并安装插件

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

### 前台启动 gateway

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py gateway \
  --profile-dir ~/.openclaw-flowhub
```

### 首访 smoke test

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py smoke \
  --profile-dir ~/.openclaw-flowhub
```

### 仅预览命令，不实际执行

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py gateway \
  --profile-dir ~/.openclaw-flowhub \
  --print-only \
  --openclaw-command /bin/echo
```

## 3. Windows 常用命令

### 初始化并安装插件

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

### 前台启动 gateway

```bat
openclaw-plugin\scripts\flowhub_openclaw_admin.cmd gateway ^
  --profile-dir %USERPROFILE%\.openclaw-flowhub
```

### 首访 smoke test

```bat
openclaw-plugin\scripts\flowhub_openclaw_admin.cmd smoke ^
  --profile-dir %USERPROFILE%\.openclaw-flowhub
```

## 4. FlowHub 后端联通性检查

### 健康检查

```bash
curl http://127.0.0.1:8000/health
```

### Run Request smoke

```bash
curl -X POST http://127.0.0.1:8000/api/v1/run-requests/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-flowhub-key" \
  -d '{
    "goal": "分析 AAPL 最近三个月走势，并返回 markdown 摘要。"
  }'
```

预期结果：

- 返回 `workflow_summary`
- 返回 `formula`
- 返回 `client_install_guidance`

## 5. OpenClaw 首访验收口径

首访消息：

```text
你好，第一次使用 FlowHub，请先介绍一下项目、主要功能、相关插件和技能清单，并告诉我怎么安装。
```

预期结果：

- 优先调用 `flowhub_handle_message`
- 返回项目介绍
- 返回插件 / Skill 清单
- 返回安装指导
- 不误创建业务工作流

## 6. 业务规划验收口径

规划消息：

```text
请使用 FlowHub 平台为我规划一个工作流：分析 AAPL 最近三个月走势，并返回 markdown 摘要。
```

预期结果：

- 返回工作流公式
- 返回选中的 Skill
- 返回安全建议
- 返回确认提示

## 7. 常见问题

### `plugins.allow: plugin not found`

原因：

- 全新 profile 在插件安装前就写入了最终插件配置

处理：

- 直接使用 `flowhub_openclaw_admin.py bootstrap --install-plugin`
- 当前脚本已自动先写预安装配置，再回写完整配置

### `openclaw: node not found`

原因：

- WSL 中 `openclaw` 包装脚本找不到 Node

处理：

- 改用：

```bash
--openclaw-command "cmd.exe /C openclaw"
```

### gateway 起不来

优先检查：

- `gateway.mode=local`
- 端口是否冲突
- 当前 profile 是否正确

建议：

- 改端口，例如 `19089`
- 先用前台 gateway，不要先依赖系统服务

### Windows `.cmd` 能运行但中文显示乱码

说明：

- 这通常是 Windows 控制台编码问题
- 不影响命令分发和实际执行

## 8. 推荐阅读

- [11-OpenClaw运行配置模板.md](./11-OpenClaw%E8%BF%90%E8%A1%8C%E9%85%8D%E7%BD%AE%E6%A8%A1%E6%9D%BF.md)
- [04-OpenClaw对接手册.md](./04-OpenClaw%E5%AF%B9%E6%8E%A5%E6%89%8B%E5%86%8C.md)
- [openclaw-plugin/README.md](/mnt/f/tool/FlowHub/openclaw-plugin/README.md)
