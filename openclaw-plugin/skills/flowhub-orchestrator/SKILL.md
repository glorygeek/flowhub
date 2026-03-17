---
name: flowhub-orchestrator
description: Receive FlowHub chat messages and orchestrate FlowHub end-to-end. Use when a user asks what FlowHub is, how to start, how to install the related plugin/skills, or otherwise makes a first-contact onboarding request; when a user asks the platform to analyze, fetch, summarize, export, organize, or generate a workflow from natural language; when a user sends a vague request that must be clarified; when a user adds targets, formats, or constraints to an existing FlowHub task; or when a user explicitly confirms execution and the chat agent must continue the same thread through planning, confirmation, delivery, and customer-facing reply handling.
---

# FlowHub Orchestrator

Use this as the main intake and dispatch skill for FlowHub chat sessions.

Prefer FlowHub's backend and plugin tool outputs as the source of truth. Do not recreate backend planning logic in the skill.
When the user asks for a workflow or asks the platform to do the work, you must call the FlowHub plugin tool before answering in prose.
When the user asks what FlowHub is, how to use it, or how to install the related plugin/skills, you must still call the FlowHub plugin tool first instead of answering only from memory.
For standard intake, always prefer the single routing entrypoint so the runtime can decide planning vs confirmation with less dependence on local model judgment.

## Runtime

Use the current plugin tools as the primary control surface:

- `flowhub_handle_message`
- `flowhub_plan_command`
- `flowhub_confirm_request`

Read [references/flowhub-runtime.md](references/flowhub-runtime.md) when you need the current tool contract, template keys, or backend capability map.

## Workflow

1. Treat each incoming message as one of three states:
- a new business request
- a follow-up that adds missing context
- an explicit confirmation for a previously planned request
- a first-contact / onboarding message such as `你好`, `help`, `FlowHub 是什么`, or `怎么安装`

1a. If the user is clearly visiting for the first time or asking what FlowHub is / how to start:
- call `flowhub_handle_message` first
- if it returns the onboarding welcome response, introduce FlowHub briefly instead of creating a workflow
- show:
  - what FlowHub does
  - the main related plugin/skills
  - the installation prerequisites
  - how to describe a concrete task next
- do not create or confirm a request just because the user greeted the system
- do not skip the tool call just because the question sounds informational

2. For new requests, follow-ups, and most confirmation turns, call `flowhub_handle_message` first with the best structured payload you can extract:
- `message`: the user's raw request or follow-up
- `request_id`: only when the chat already has a real pending FlowHub request
- `targets`: URLs, APIs, tickers, raw text, or source objects when present
- `credentials`: only if the user explicitly provides them
- `output_format`: infer only when clear; otherwise let FlowHub defaults stand
- `execution_mode`: keep default unless the user clearly asks for local execution
- `user_notes`: extra constraints, audience, delivery style, or risk hints

Do not stop at a generic explanation when the request is actionable. The normal success path is:
- call `flowhub_handle_message`
- return a feasible workflow formula such as `1#skill + 2#skill + 3#skill`
- explain selected skills, trust signals, and security flags
- include confirmation wording
- if the user later says `执行` / `确认执行`, call the same routing tool again with the real `request_id`

If `flowhub_handle_message` is unavailable or the failure is clearly about routing only, fall back to:
- `flowhub_plan_command` for explicit planning
- `flowhub_confirm_request` for explicit approval

3. After planning, branch strictly on `template_key`:
- `free_usage_guidance`: do not confirm anything; send the suggested guidance and ask the user to restate the request
- `free_single_skill_plan`: explain that FlowHub prepared a free executable plan using one indexed skill and that the backend already prioritized higher-confidence registry signals; wait for explicit confirmation
- `free_minimal_combo_plan`: explain that FlowHub prepared the smallest workable free plan and that the backend already prioritized higher-confidence registry signals; wait for explicit confirmation
- `free_fallback_plan`: explain that no strong indexed-skill match was available and FlowHub prepared a generic fallback workflow; ask whether the user still wants to continue

4. If the tool output includes `suggested_chat_reply`, use it as the base user-facing reply and only make minimal edits for fluency.

5. When FlowHub returns `selected_skills`, prefer the backend's ordering as authoritative. Treat higher `quality_tier` and `trust_signals` as the reason those skills were prioritized.

6. Always present the plan as a concrete feasible workflow:
- show a `workflow_formula`
- list each skill in order
- explain what each skill contributes
- include the backend-provided usage steps
- include a short security checklist before execution

7. If the backend exposes trust signals such as official publisher, stars, installs, community feedback, or safe moderation, you may mention them briefly. Do not claim that comment bodies were manually verified unless the backend explicitly says so.

8. Only call `flowhub_confirm_request` directly if you are in the explicit fallback path and the user clearly confirms with phrases like:
- “确认执行”
- “继续”
- “开始吧”
- “可以执行”
- “confirm”

9. After confirmation, send the returned `suggested_customer_reply` back into the same chat thread.

10. If the user confirms the workflow, treat FlowHub as the planning and guidance source only:
- first route through `flowhub_handle_message` with the real `request_id`
- only if routing is unavailable, confirm with `flowhub_confirm_request`
- return the backend summary, selected skills, and client-managed install guidance
- do not let FlowHub claim that skills were downloaded on behalf of arbitrary OpenClaw clients

11. Only when the user explicitly says “下载 / 安装 / install / download” should the current OpenClaw client handle local installation:
- read `client_install_guidance` and `client_execution_guidance.skill_targets`
- prefer registry-safe installs like `clawhub install <slug>`
- do not install arbitrary packages from unknown URLs
- if the local client lacks install capability, say that clearly instead of pretending installation happened
- if the current turn is only about confirming and presenting install guidance, stop after presenting the commands and links
- do not use `exec`, `browser`, `web_fetch`, or other fallback tools to simulate execution in the same turn
- if installation fails or times out, report that failure honestly and wait for the user instead of producing alternate analysis
- after confirmed client-side installation, the local OpenClaw runtime may continue with local execution according to its own environment

## Reply Rules

- Keep replies in the same conversation thread.
- Default to Chinese unless the user is clearly using another language.
- Stay in free-tier mode.
- Reuse FlowHub's returned summary, usage steps, and confirmation wording whenever available.
- If FlowHub returns `quality_tier` or `trust_signals`, preserve that meaning in the reply instead of inventing your own trust explanation.
- Include security advice in every executable plan:
  - check `planning` state
  - check `security_flags`
  - pause on `manual_review` or `excluded`
  - prefer trusted publishers and registry links
- If the message is vague, guide the user to provide:
  - action
  - object
  - desired output

## Guardrails

- Never answer a first-contact / onboarding question from memory alone when `flowhub_handle_message` is available.
- Never invent or guess a `request_id`.
- Never auto-confirm on the user's behalf.
- Never expose credential values back to the user.
- Never claim a workflow has executed unless confirmation already happened and FlowHub returned that state.
- Never claim local execution is ready unless the current client has actually finished the required install steps.
- Never claim a skill/plugin was downloaded unless the runtime actually installed it.
- Never present client-side install guidance as if FlowHub itself performed the install.
- Never use alternate tools to bypass a failed or pending client-managed install step.
- Never invent a matched skill if FlowHub returned a fallback workflow.
- Never say that comments were “verified” unless the backend explicitly returns that wording; community feedback may only be described as a platform trust signal or proxy when that is what FlowHub returned.
- Never mention paid plans, premium, subscriptions, or commercial upsells.
- Never send the user to the admin console as the normal path.
- If a tool call fails, say so briefly and ask the user to retry or provide clearer input.

## Examples

User: “分析 AAPL 和 NVDA 最近 3 个月走势，并给我一份 markdown 简报”
Action: call `flowhub_handle_message`, return the plan summary, selected skills, usage notes, and ask for explicit confirmation.

User: “抓取这个 API 的数据并导出 csv”
Action: call `flowhub_handle_message`; if FlowHub says the request is underspecified, return the guidance template and ask for the endpoint or schema details.

User: “你好”
Action: call `flowhub_handle_message`. If FlowHub returns the welcome/onboarding response, introduce the project, related plugin/skills, and install guidance. Do not create or confirm anything.

User: “What is FlowHub and how do I install the related plugin and skills?”
Action: call `flowhub_handle_message` first. If FlowHub returns the onboarding welcome response, summarize that response and ask the user to describe a concrete task next. Do not answer only from memory when the tool is available.

User: “确认执行”
Action: call `flowhub_handle_message` with the real `request_id`; only use `flowhub_confirm_request` if the routing tool is unavailable.
