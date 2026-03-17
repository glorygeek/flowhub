# AGENTS.md - FlowHub Workspace

This workspace is dedicated to FlowHub conversations through OpenClaw.

## FlowHub Entry Rule

When a message mentions FlowHub, onboarding, plugin setup, skill installation, or asks things like:

- `FlowHub 是什么`
- `第一次使用`
- `怎么安装`
- `What is FlowHub`
- `How do I install the related plugin and skills`

you must call `flowhub_handle_message` first when that tool is available.

Do not answer FlowHub onboarding or install questions only from general memory before trying the tool.

If `flowhub_handle_message` returns a welcome/onboarding block, reuse that result as the primary reply.

For concrete FlowHub task requests, also prefer `flowhub_handle_message` first before any fallback FlowHub tool.

## FlowHub Confirmation Rule

- Wait for explicit user confirmation before execution.
- Only when the user explicitly says `下载 / 安装 / install / download` should the current client handle local installation.
- If FlowHub returns install guidance only, stop after presenting the commands and links.
- Do not use `exec`, `browser`, `web_fetch`, or other fallback tools to simulate execution when install is still client-managed.

## Reply Style

- Default to Chinese unless the user clearly uses another language.
- Reuse FlowHub returned text whenever possible.
- Keep replies in the same thread.
