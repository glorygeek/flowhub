# FlowHub Skill Review Runtime

Use this reference only when reviewing or escalating skill safety inside FlowHub.

## Backend evidence to trust first

- `GET /api/v1/skills/search`
  - returns ranked candidates with `quality_*` and `security_*` fields
- `GET /api/v1/skills/{skill_id}`
  - returns the stored skill contract plus computed security posture
- `GET /api/v1/skills/{skill_id}/security-review`
  - returns:
    - `security_score`
    - `security_tier`
    - `security_verdict`
    - `security_flags`
    - `permission_profile`
    - `moderation_verdict`

## Security tier meaning

- `safe`
  - no obvious red flags in current metadata
  - still not equal to full source-code audit
- `caution`
  - privileged behavior exists but is not automatically blocking
  - use only with clear operator awareness
- `review`
  - manual operator review should happen before workflow promotion
- `block`
  - quarantine or exclude from customer-facing planning unless a human explicitly overrides

## Typical red-flag buckets

- credential or token access
- shell or command execution
- external state write
- dynamic execution or encoded payload hints
- sensitive config or identity file access
- suspicious moderation verdict

## Operator phrasing guidance

Prefer short, concrete language:

- "This skill is suitable for controlled use."
- "This skill should stay behind manual review."
- "This skill should be quarantined from default planning."

Avoid overstating confidence. Metadata-based review is not a full code audit.
