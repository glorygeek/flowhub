# FlowHub OpenClaw Plugin

This plugin lets an OpenClaw agent call FlowHub during a chat conversation instead of sending users to a separate web form.

Primary orchestration skill:

- `skills/flowhub-orchestrator`
- `skills/flowhub-skill-discovery`

Internal-only maintenance skill kept in the library but not enabled for the customer-facing plugin manifest:

- `skills/flowhub-self-improvement`
- `skills/flowhub-skill-vetter`
- Internal maintenance plugin package: `internal-maintenance/openclaw.plugin.json`

## Tools

- `flowhub_search_skills`
  - search the indexed FlowHub skill catalog
  - returns trusted candidate skills ranked by relevance and registry trust signals
- `flowhub_plan_command`
  - create a planned workflow from a natural-language command
  - returns `request_id`, `workflow_id`, selected skills, usage notes, and a confirmation prompt
- `flowhub_confirm_request`
  - confirm a previously planned request
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

1. User sends a command in chat.
2. Agent calls `flowhub_plan_command`.
3. Agent replies with the workflow summary, selected skills, usage notes, and asks for confirmation.
4. User confirms in chat.
5. Agent calls `flowhub_confirm_request`.
6. Agent sends the returned customer-facing reply payload in the same thread.
