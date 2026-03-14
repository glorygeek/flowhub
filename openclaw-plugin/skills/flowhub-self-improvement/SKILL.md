---
name: flowhub-self-improvement
description: Internal maintenance skill for sanitized learning capture, incident notes, and postmortem follow-up. Use only in developer or operator sessions when a maintainer explicitly wants to record a reusable lesson, recurring failure, or missing capability. Do not use in external customer conversations.
---

# FlowHub Self Improvement

Use this only for internal maintenance work. This skill is not for user-facing bot replies.

Read [references/log-sanitization.md](references/log-sanitization.md) before recording any learning or postmortem note.

## When To Use

- A maintainer asks to record a recurring issue
- A deployment or integration failure revealed a reusable lesson
- A user correction exposed a durable product or engineering gap
- A missing capability should be tracked for future implementation

## Workflow

1. Confirm the session is internal maintenance, not an external customer chat.
2. Capture the smallest useful learning.
3. Sanitize before writing anything down.
4. Prefer project-local learnings or internal ops notes over global workspace memory.
5. Promote only stable, broadly useful rules into long-lived instructions.

## Sanitization Rules

- Never log API keys, tokens, cookies, auth headers, passwords, private URLs with secrets, or raw credentials.
- Never log customer PII, contact details, account identifiers, portfolio holdings, or private conversation text unless the maintainer explicitly asks and the data is redacted.
- Replace sensitive strings with placeholders such as `[REDACTED_TOKEN]`, `[REDACTED_EMAIL]`, or `[REDACTED_CUSTOMER_INPUT]`.
- Summarize failures instead of copying full raw transcripts.
- Do not read or send another session's transcript unless a maintainer explicitly requests it and the output is sanitized first.

## Guardrails

- Never enable hooks globally for a customer-facing bot by default.
- Never auto-promote a learning into memory files without checking that it is general and safe.
- Never treat customer-facing chats as a logging surface.
- Never use cross-session tools to copy raw customer content.

## Examples

Maintainer: “把这次 Docker 构建失败记录成一条经验”
Action: capture a sanitized internal learning with the failing command pattern, root cause, and fix. Exclude secrets and irrelevant raw output.

Maintainer: “这个用户刚才发来的授权信息导致错误，记下来”
Action: do not copy the raw authorization content. Record only the abstract failure mode and redact all sensitive values.
