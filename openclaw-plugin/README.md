# FlowHub OpenClaw Plugin

This plugin lets an OpenClaw agent call FlowHub during a chat conversation instead of sending users to a separate web form.

Primary customer-facing orchestration skill:

- `skills/flowhub-orchestrator`

Related optional support skills kept in the library:

- `skills/flowhub-skill-discovery`

Internal-only maintenance skill kept in the library but not enabled for the customer-facing plugin manifest:

- `skills/flowhub-self-improvement`
- `skills/flowhub-skill-vetter`
- Internal maintenance plugin package: `internal-maintenance/openclaw.plugin.json`

## Tools

- `flowhub_handle_message`
  - single preferred FlowHub chat entrypoint
  - handles onboarding, install guidance, workflow planning, follow-up context, and confirmation routing
- `flowhub_search_skills`
  - search the indexed FlowHub skill catalog
  - returns trusted candidate skills ranked by relevance and registry trust signals
  - use only for discovery-first requests; otherwise prefer `flowhub_handle_message`
- `flowhub_plan_command`
  - fallback-only planning tool when routing is unavailable
  - returns `request_id`, `workflow_id`, selected skills, usage notes, and a confirmation prompt
- `flowhub_confirm_request`
  - fallback-only confirmation tool when routing is unavailable
  - returns the customer-facing reply payload that should be sent back into the same chat

## Install locally

```bash
openclaw plugins install ./openclaw-plugin
```

Internal maintenance plugin:

```bash
openclaw plugins install ./openclaw-plugin/internal-maintenance
```

OpenClaw docs say local folders are valid plugin install sources and every plugin must ship `openclaw.plugin.json`.

Reusable config templates:

- [examples/openclaw.local.sample.jsonc](/mnt/f/tool/FlowHub/openclaw-plugin/examples/openclaw.local.sample.jsonc)
- [examples/openclaw.vps.sample.jsonc](/mnt/f/tool/FlowHub/openclaw-plugin/examples/openclaw.vps.sample.jsonc)
- [examples/flowhub.workspace.AGENTS.sample.md](/mnt/f/tool/FlowHub/openclaw-plugin/examples/flowhub.workspace.AGENTS.sample.md)

Recommended deployment pattern:

- create a dedicated OpenClaw agent such as `flowhub`
- give it a dedicated workspace such as `~/.openclaw/workspace-flowhub`
- copy [examples/flowhub.workspace.AGENTS.sample.md](/mnt/f/tool/FlowHub/openclaw-plugin/examples/flowhub.workspace.AGENTS.sample.md) to that workspace as `AGENTS.md`
- keep `flowhub_handle_message` as the normal first tool for onboarding, planning, and confirmation

Bootstrap shortcut:

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

Windows wrapper:

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

If `openclaw` must be invoked through a wrapper shell, pass it explicitly:

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
  --openclaw-command "cmd.exe /C openclaw"
```

Safe validation without touching a real OpenClaw install:

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py bootstrap \
  --mode local \
  --profile-dir /tmp/.openclaw-flowhub-check \
  --workspace-dir /tmp/openclaw-workspace-flowhub-check \
  --api-base-url http://127.0.0.1:8000/api/v1 \
  --api-key bootstrap-check-key \
  --install-plugin \
  --validate-profile \
  --check-plugins \
  --openclaw-command /bin/echo
```

Optional post-bootstrap actions:

- `--validate-profile`
- `--check-plugins`
- `--start-gateway-service`
- `--gateway-health-check`
- `--smoke-test`
- `--run-gateway-foreground`

Foreground gateway helper:

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py gateway \
  --profile-dir ~/.openclaw-flowhub
```

If OpenClaw must be invoked through Windows `cmd`:

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py gateway \
  --profile-dir /mnt/c/Users/Administrator/.openclaw-flowhub \
  --openclaw-command "cmd.exe /C openclaw"
```

First-contact smoke-test helper:

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py smoke \
  --profile-dir ~/.openclaw-flowhub
```

Windows wrapper:

```bat
openclaw-plugin\scripts\flowhub_openclaw_admin.cmd smoke ^
  --profile-dir %USERPROFILE%\.openclaw-flowhub
```

Example with a first-contact smoke test:

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

Preview the foreground gateway command without actually starting it:

```bash
python3 ./openclaw-plugin/scripts/flowhub_openclaw_admin.py bootstrap \
  --mode local \
  --profile-dir ~/.openclaw-flowhub \
  --workspace-dir ~/.openclaw/workspace-flowhub \
  --api-base-url http://127.0.0.1:8000/api/v1 \
  --api-key your-flowhub-api-key \
  --run-gateway-foreground \
  --run-gateway-print-only
```

## Example config

```json5
{
  plugins: {
    load: { paths: ["/path/to/FlowHub/openclaw-plugin"] },
    entries: {
      "flowhub-openclaw": {
        enabled: true,
        config: {
          apiBaseUrl: "http://127.0.0.1:8000/api/v1",
          apiKey: "dev-flowhub-key",
          timeoutMs: 20000,
          defaultExecutionMode: "remote",
          defaultOutputFormat: "markdown"
        }
      }
    }
  },
  agents: {
    list: [
      {
        id: "flowhub",
        name: "FlowHub",
        workspace: "~/.openclaw/workspace-flowhub",
        tools: {
          allow: ["flowhub-openclaw"]
        }
      }
    ]
  },
  bindings: [
    {
      match: { channel: "telegram" },
      agentId: "flowhub"
    }
  ]
}
```

## Chat behavior

1. If the user first arrives with a greeting or asks what FlowHub is, the agent returns a short project introduction, related plugin/skill list, and install prerequisites.
2. If the user sends a concrete task, the agent should call `flowhub_handle_message` first.
3. Agent replies with the workflow summary, selected skills, usage notes, and asks for confirmation.
4. User confirms in chat.
5. Agent should call `flowhub_handle_message` first for confirmation turns and only fall back to `flowhub_confirm_request` if routing is unavailable.
6. Agent sends the returned customer-facing reply payload in the same thread.
7. If the user explicitly says `下载 / 安装 / install / download`, the reply also includes client-managed install guidance such as:

```text
客户端安装方式：
1. 通用命令：clawhub install us-stock-analysis
   Windows 命令：clawhub.cmd install us-stock-analysis
   Skill 地址：https://clawhub.ai/api/v1/skills/us-stock-analysis
```

FlowHub only returns the workflow and install instructions. The current OpenClaw client decides whether to execute those install commands locally.
