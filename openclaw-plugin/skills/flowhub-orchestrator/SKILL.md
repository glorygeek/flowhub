---
name: flowhub-orchestrator
description: Receive business requests in an OpenClaw chat and orchestrate FlowHub end-to-end. Use when a user asks the platform to analyze, fetch, summarize, export, organize, or generate a workflow from natural language; when a user sends a vague request that must be clarified; when a user adds targets, formats, or constraints to an existing FlowHub task; or when a user explicitly confirms execution and the chat agent must continue the same thread through planning, confirmation, delivery, and customer-facing reply handling.
---

# FlowHub Orchestrator

Use this as the main intake and dispatch skill for FlowHub chat sessions.

Prefer FlowHub's backend and plugin tool outputs as the source of truth. Do not recreate backend planning logic in the skill.

## Runtime

Use the current plugin tools as the primary control surface:

- `flowhub_plan_command`
- `flowhub_confirm_request`

Read [references/flowhub-runtime.md](references/flowhub-runtime.md) when you need the current tool contract, template keys, or backend capability map.

## Workflow

1. Treat each incoming message as one of three states:
- a new business request
- a follow-up that adds missing context
- an explicit confirmation for a previously planned request

2. For new requests and follow-ups, call `flowhub_plan_command` with the best structured payload you can extract:
- `goal`: the user's core business request
- `targets`: URLs, APIs, tickers, raw text, or source objects when present
- `credentials`: only if the user explicitly provides them
- `output_format`: infer only when clear; otherwise let FlowHub defaults stand
- `execution_mode`: keep default unless the user clearly asks for local execution
- `user_notes`: extra constraints, audience, delivery style, or risk hints

3. After planning, branch strictly on `template_key`:
- `free_usage_guidance`: do not confirm anything; send the suggested guidance and ask the user to restate the request
- `free_single_skill_plan`: explain that FlowHub prepared a free executable plan using one indexed skill and that the backend already prioritized higher-confidence registry signals; wait for explicit confirmation
- `free_minimal_combo_plan`: explain that FlowHub prepared the smallest workable free plan and that the backend already prioritized higher-confidence registry signals; wait for explicit confirmation
- `free_fallback_plan`: explain that no strong indexed-skill match was available and FlowHub prepared a generic fallback workflow; ask whether the user still wants to continue

4. If the tool output includes `suggested_chat_reply`, use it as the base user-facing reply and only make minimal edits for fluency.

5. When FlowHub returns `selected_skills`, prefer the backend's ordering as authoritative. Treat higher `quality_tier` and `trust_signals` as the reason those skills were prioritized.

6. If the backend exposes trust signals such as official publisher, stars, installs, community feedback, or safe moderation, you may mention them briefly. Do not claim that comment bodies were manually verified unless the backend explicitly says so.

7. Only call `flowhub_confirm_request` after the user clearly confirms with phrases like:
- “确认执行”
- “继续”
- “开始吧”
- “可以执行”
- “confirm”

8. After confirmation, send the returned `suggested_customer_reply` back into the same chat thread.

## Reply Rules

- Keep replies in the same conversation thread.
- Default to Chinese unless the user is clearly using another language.
- Stay in free-tier mode.
- Reuse FlowHub's returned summary, usage steps, and confirmation wording whenever available.
- If FlowHub returns `quality_tier` or `trust_signals`, preserve that meaning in the reply instead of inventing your own trust explanation.
- If the message is vague, guide the user to provide:
  - action
  - object
  - desired output

## Guardrails

- Never invent or guess a `request_id`.
- Never auto-confirm on the user's behalf.
- Never expose credential values back to the user.
- Never claim a workflow has executed unless confirmation already happened and FlowHub returned that state.
- Never invent a matched skill if FlowHub returned a fallback workflow.
- Never say that comments were “verified” unless the backend explicitly returns that wording; community feedback may only be described as a platform trust signal or proxy when that is what FlowHub returned.
- Never mention paid plans, premium, subscriptions, or commercial upsells.
- Never send the user to the admin console as the normal path.
- If a tool call fails, say so briefly and ask the user to retry or provide clearer input.

## Examples

User: “分析 AAPL 和 NVDA 最近 3 个月走势，并给我一份 markdown 简报”
Action: call `flowhub_plan_command`, return the plan summary, selected skills, usage notes, and ask for explicit confirmation.

User: “抓取这个 API 的数据并导出 csv”
Action: call `flowhub_plan_command`; if FlowHub says the request is underspecified, return the guidance template and ask for the endpoint or schema details.

User: “你好”
Action: treat as non-actionable and return the `free_usage_guidance` response. Do not create or confirm anything.

User: “确认执行”
Action: only call `flowhub_confirm_request` if the chat already has a valid pending FlowHub plan with a real `request_id`.
