---
name: flowhub-skill-vetter
description: Review third-party or newly synced skills for FlowHub security posture before they are promoted into customer-facing workflows. Use for internal skill vetting, safety labeling, suspicious capability review, and operator-facing approval decisions.
---

# FlowHub Skill Vetter

Internal-only skill for reviewing skill safety posture inside FlowHub.

Prefer FlowHub backend outputs as the source of truth. Reuse:

- `security_tier`
- `security_verdict`
- `security_flags`
- `quality_tier`
- `trust_signals`
- source metadata such as `source`, `source_slug`, `source_url`, `owner_handle`

Read [references/skill-review-runtime.md](references/skill-review-runtime.md) when you need the current FlowHub security-review fields and how they map to operator actions.

## Workflow

1. Use this skill when:
- a new external skill is being evaluated
- an indexed skill looks suspicious or unusually privileged
- an operator needs a concise approval or quarantine recommendation

2. Start from backend evidence:
- ranked search diagnostics
- skill detail metadata
- security review endpoint output
- operator tag history when relevant

3. Produce a short operator-facing conclusion:
- what the skill claims to do
- which capabilities increase risk
- whether current evidence supports `safe_to_use`, `use_with_caution`, `manual_review_required`, or `block_or_quarantine`

4. If evidence is incomplete:
- say that directly
- request a deeper manual review
- do not invent code-level findings that the backend has not surfaced

## Guardrails

- Never install a remote skill directly from chat.
- Never recommend `npm install -g`, `npx skills add`, or similar remote install commands as a normal review step.
- Never claim code was fully audited unless all files were actually reviewed.
- Never downplay `credential_access`, `command_execution`, `external_write`, suspicious moderation, or dynamic-execution signals.
- Treat backend `security_tier=block` as quarantine unless a human explicitly overrides it.
- Keep this skill for internal review and maintenance, not customer-facing bot replies.

## Output

Return:
- security summary
- key red flags
- permission scope summary
- operator recommendation

Keep the recommendation concise and decision-oriented.
