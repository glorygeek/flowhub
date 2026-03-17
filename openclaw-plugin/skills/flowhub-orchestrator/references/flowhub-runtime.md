# FlowHub Runtime

## Current tool surface

### `flowhub_handle_message`

Use this as the default chat entrypoint.

This should also be the default entrypoint for onboarding questions such as:
- `你好`
- `第一次使用 FlowHub`
- `FlowHub 是什么`
- `怎么安装`
- `What is FlowHub?`
- `How do I install the related plugin and skills?`

Inputs:
- `message`: required raw user message
- `request_id`: optional real FlowHub request id for confirmation turns
- `targets`: optional array of `{type,label,value}`
- `credentials`: optional array of `{label,kind,value,ephemeral}`
- `output_format`: optional `json|csv|xlsx|pdf|markdown`
- `execution_mode`: optional `remote|local`
- `user_notes`: optional extra constraints

Important behavior:
- If the message looks like a first-contact / onboarding request such as `你好`, `help`, `FlowHub 是什么`, or `怎么安装`, the plugin may return a welcome block instead of creating a workflow
- If the message looks like explicit confirmation and a real `request_id` is present, the plugin routes to `POST /api/v1/run-requests/{id}/confirm`
- Otherwise the plugin routes to `POST /api/v1/run-requests/`
- Returns the same backend plan/confirm payloads as the explicit tools, but with less routing burden on the model
- For confirm turns, the plugin now returns client-managed install guidance instead of attempting local installation itself

Welcome/onboarding response includes:
- basic FlowHub project summary
- main related plugin and skill list
- install prerequisites (`flowhub-openclaw`, `apiBaseUrl`, `apiKey`)
- safe-install note: only explicit user download/install requests should trigger local client-side install commands

Agent rule:
- When `flowhub_handle_message` is available, do not answer onboarding questions only from general memory.
- Call the tool first, then reuse the returned onboarding block.

### `flowhub_plan_command`

Use as a fallback for explicit planning when the routing entrypoint is unavailable.

Inputs:
- `goal`: required natural-language task
- `targets`: optional array of `{type,label,value}`
- `credentials`: optional array of `{label,kind,value,ephemeral}`
- `output_format`: optional `json|csv|xlsx|pdf|markdown`
- `execution_mode`: optional `remote|local`
- `user_notes`: optional extra constraints

Important behavior:
- Calls `POST /api/v1/run-requests/`
- Lets the backend decide whether the message is actionable
- Returns `template_key`, `selected_skills`, usage steps, confirmation guidance, and skill trust metadata such as `quality_tier` and `trust_signals`
- May return `request_id` and `workflow_id` when a plan was created
- The plugin text wrapper also renders a `workflow_formula` based on selected skill order, for example `1#clawhub/us-stock-analysis + 2#output.export`
- The plugin text wrapper prefers backend `workflow_summary` when available and also adds `security_guidance` so the chat reply can show execution caveats before the user confirms

### `flowhub_confirm_request`

Use only after explicit confirmation and only as a fallback when the routing entrypoint is unavailable.

Inputs:
- `request_id`

Important behavior:
- Calls `POST /api/v1/run-requests/{id}/confirm`
- Returns the customer-facing reply payload for the same chat thread
- Also returns client-managed install guidance such as:
  - `install_mode: client_managed`
  - `install_requested: yes|no`
  - `install_status: deferred|pending_client_action|not_required`
  - `install_targets`

## Template keys

### `free_usage_guidance`

Meaning:
- The message is not actionable enough to create a workflow

Agent behavior:
- Do not confirm
- Ask the user to restate the request
- Reuse `suggested_chat_reply`

### `free_single_skill_plan`

Meaning:
- FlowHub found one indexed skill that can independently satisfy the request

Agent behavior:
- Explain that a free executable plan is ready
- Show the skill intro and usage guidance
- Wait for explicit confirmation

### `free_minimal_combo_plan`

Meaning:
- One skill was not enough, so FlowHub created the smallest workable combination

Agent behavior:
- Explain that this is the minimal viable free plan
- Wait for explicit confirmation

### `free_fallback_plan`

Meaning:
- FlowHub did not find a strong indexed-skill match and created a generic fallback workflow

Agent behavior:
- Say it is a generic fallback plan
- Ask whether the user still wants to continue

## Backend capability map

The backend already handles:
- non-demand detection
- AI-assisted intake analysis
- AI-assisted skill/workflow planning
- AI-assisted reply rewriting
- skill catalog search
- trust-aware skill reranking using stars, installs, downloads, moderation, and community-feedback proxies
- workflow creation
- confirmation-stage reply generation

The skill should orchestrate these capabilities, not reimplement them.

## Execution expectation

For actionable requests, the expected final chat response is:

1. a feasible workflow formula
2. selected skills in backend order
3. usage steps
4. security guidance
5. an explicit confirmation prompt

For first-contact requests, the expected final chat response is:

1. a brief FlowHub introduction
2. simple explanation of what kinds of tasks the platform can handle
3. the related plugin/skill list
4. install guidance for the current OpenClaw client
5. one prompt asking the user to describe a concrete task next

If the user later says `执行` / `确认执行`, FlowHub should only return workflow confirmation plus install guidance:

- read `client_execution_guidance.skill_targets`
- read `client_install_guidance`
- only if the user explicitly asks to install or download should the local OpenClaw client run commands such as `clawhub install <slug>`
- keep plugin/skill downloads restricted to trusted registry targets
- never claim that a download happened unless the local client actually succeeded
- when `client_install_guidance.status=pending_client_action`, stop after presenting the install guidance
- do not call `exec`, `browser`, `web_fetch`, or any fallback execution tool to bypass that step
- if installation fails or times out, return the failure and wait for the user instead of generating substitute analysis

## Conversation principles

- Keep all interaction in the same chat thread
- Prefer backend-produced wording over ad hoc rewrites
- Treat backend-provided trust signals as authoritative and do not upgrade a proxy signal into a stronger claim
- Use Chinese by default
- Never expose secrets
- Never auto-confirm
