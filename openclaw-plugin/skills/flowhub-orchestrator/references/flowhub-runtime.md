# FlowHub Runtime

## Current tool surface

### `flowhub_plan_command`

Use for almost every new business request or follow-up.

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

### `flowhub_confirm_request`

Use only after explicit confirmation.

Inputs:
- `request_id`

Important behavior:
- Calls `POST /api/v1/run-requests/{id}/confirm`
- Returns the customer-facing reply payload for the same chat thread

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

## Conversation principles

- Keep all interaction in the same chat thread
- Prefer backend-produced wording over ad hoc rewrites
- Treat backend-provided trust signals as authoritative and do not upgrade a proxy signal into a stronger claim
- Use Chinese by default
- Never expose secrets
- Never auto-confirm
