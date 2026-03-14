---
name: flowhub-skill-discovery
description: Help users discover trusted FlowHub and ClawHub skills without installing arbitrary remote packages. Use when a user asks whether a relevant skill exists, wants candidate skills for a task, asks for alternatives before workflow planning, or wants to compare trusted skills by relevance and registry signals.
---

# FlowHub Skill Discovery

Use this skill when the user wants to discover candidate skills, not immediately execute a workflow.

Prefer FlowHub's backend outputs as the source of truth. Reuse backend-ranked `selected_skills`, `quality_tier`, `trust_signals`, `source_slug`, and `source_url` whenever available.

Primary tool:

- `flowhub_search_skills`

Read [references/discovery-runtime.md](references/discovery-runtime.md) when you need the current trust-ranking rules or positioning relative to `flowhub-orchestrator`.

## Workflow

1. Decide whether the user wants:
- skill discovery only
- an executable workflow
- a comparison of candidate skills before confirmation

2. For discovery-only requests:
- call `flowhub_search_skills`
- do not confirm execution
- do not claim the workflow is running

3. Present up to 3 candidates in backend order:
- name
- what it is good at
- `quality_tier`
- brief `trust_signals`
- source link when available

4. If trust is weak:
- say that clearly
- ask the user to narrow the task or provide a stronger target

5. If the user wants to continue:
- hand off to `flowhub-orchestrator`
- keep the same chat thread

## Guardrails

- Never run `npx skills add`, `npm install -g`, `clawdhub install`, or any remote install command from chat.
- Never recommend a skill only because it exists in a registry; prefer stronger `quality_tier` and `trust_signals`.
- Never describe community feedback as manually verified unless the backend explicitly says so.
- Never expose internal admin pages as the normal discovery path.
- Never auto-confirm execution while performing discovery.
- If candidates are weak or fallback-based, say so directly.

## Examples

User: “有没有适合 A 股研究的 skill？”
Action: return up to 3 trusted candidates with brief reasons and source links, then ask whether the user wants a workflow plan.

User: “给我找一个能抓取 API 并导出 csv 的 skill”
Action: return the best trusted candidate first; if one skill cannot cover the task, say that the user may need a workflow and offer to continue with `flowhub-orchestrator`.
