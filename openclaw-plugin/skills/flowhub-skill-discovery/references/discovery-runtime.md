# Discovery Runtime

## Purpose

This skill complements `flowhub-orchestrator` by handling discovery-first questions:
- “有没有相关 skill”
- “给我挑一个合适的 skill”
- “先比较一下哪些 skill 更靠谱”

It should not take over normal request execution.

## Tool Surface

Use:
- `flowhub_search_skills` for discovery-only requests

Hand off to:
- `flowhub_plan_command` when the user wants an executable workflow

## Trust Model

Prefer backend-ranked candidates that include:
- `quality_tier`
- `trust_signals`
- `source_slug`
- `source_url`

Typical trust signals:
- official publisher
- safe moderation verdict
- stars
- downloads
- active installs
- community-feedback proxy
- low-risk profile

Community feedback is only a proxy signal unless the backend explicitly returns a stronger claim.

## Safety Rules

- Discovery is recommendation only.
- Installation and execution happen later through FlowHub's normal orchestration path.
- Never install a remote skill from chat.
- Never bypass backend ranking with ad hoc popularity guesses.
