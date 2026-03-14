# FlowHub MVP

Monorepo for FlowHub MVP:
- `backend/` FastAPI + SQLAlchemy + Alembic
- `frontend/` Next.js App Router console
- `client/` Tauri + TypeScript runtime
- `openclaw-plugin/` OpenClaw chat bridge
- `codex-scripts/` code template generators

## Documentation

- [PROJECT_GUIDE.md](/mnt/f/tool/FlowHub/PROJECT_GUIDE.md): 全量综合说明
- [DEVELOPER_GUIDE.md](/mnt/f/tool/FlowHub/DEVELOPER_GUIDE.md): 开发、部署、联调说明
- [PRODUCT_OVERVIEW.md](/mnt/f/tool/FlowHub/PRODUCT_OVERVIEW.md): 产品、业务、客户说明
- [商业.md](/mnt/f/tool/FlowHub/%E5%95%86%E4%B8%9A.md): 免费版与后续商业化参考方案
- [docs/delivery/README.md](/mnt/f/tool/FlowHub/docs/delivery/README.md): 正式交付文档入口
- [docs/delivery/06-后续任务清单.md](/mnt/f/tool/FlowHub/docs/delivery/06-%E5%90%8E%E7%BB%AD%E4%BB%BB%E5%8A%A1%E6%B8%85%E5%8D%95.md): 当前未闭环事项与执行顺序
- [docs/delivery/07-发布前检查清单.md](/mnt/f/tool/FlowHub/docs/delivery/07-%E5%8F%91%E5%B8%83%E5%89%8D%E6%A3%80%E6%9F%A5%E6%B8%85%E5%8D%95.md): 发布前最终检查
- [docs/delivery/08-基线提交建议.md](/mnt/f/tool/FlowHub/docs/delivery/08-%E5%9F%BA%E7%BA%BF%E6%8F%90%E4%BA%A4%E5%BB%BA%E8%AE%AE.md): 首个基线提交建议

## Quick start

1. Backend:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

2. Frontend:
```bash
cd frontend
npm install
npm run dev
```

3. Client runtime:
```bash
cd client
npm install
npm run run-workflow -- --spec ./sample-workflow.json
```

Plan bundle fetch demo:
```bash
cd client
npm run run-plan
```

Client AI runtime:
```bash
cd client
npm run run-plan
```

The client runtime now:
- fetches referenced skills from the official registry,
- retries on `429` and falls back to local cache,
- writes a `resolved workflow` file locally,
- uses a client-side OpenAI-compatible model when `CLIENT_AI_*` is configured,
- falls back to simulated execution if the client AI request fails.

Client AI configuration can live in `client/.env`. If those values are absent, the runtime will also reuse `backend/.env` AI settings in this repo for local validation.

## API auth

Set `X-API-Key` header with `FLOWHUB_API_KEY` value.

## Daily ClawHub skill index sync

The backend now syncs the public ClawHub skill registry into the local `skills` table.

Manual run:

```bash
cd backend
python scripts/sync_clawhub_skills.py
```

Daily schedule:

- `CLAWHUB_SYNC_ENABLED=true`
- `CLAWHUB_SYNC_CRON=0 3 * * *`
- `CLAWHUB_SYNC_TIMEZONE=Asia/Shanghai`

Manual API trigger:

```bash
curl -X POST \
  -H "X-API-Key: dev-flowhub-key" \
  "http://localhost:8000/api/v1/skills/sync/clawhub"
```

## Skill search and tag index

The backend now keeps a local tag library on top of synced and manually added skills.

- `GET /api/v1/skills/search?q=...`
- `GET /api/v1/skills/search/policies`
- `GET /api/v1/skills/tags`
- `GET /api/v1/skills/?tags=domain:china_equity,quality:trusted`
- `GET /api/v1/skills/{skill_id}/security-review`
- `PUT /api/v1/skills/{skill_id}/security-review`
- `GET /api/v1/skills/{skill_id}/security-history`
- `GET /api/v1/skills/{skill_id}/security-history/export`
- `GET /api/v1/skills/{skill_id}/tag-history`
- `GET /api/v1/skills/search/policies/{rule_id}/history`
- `POST /api/v1/skills/search/policies/{rule_id}/rollback/{log_id}`

The planner uses this index together with quick search ranking, quality signals, market-domain routing, configurable request-policy rules, and metadata-based security review for A股、美股、API 抓取、客户回复等高价值场景 so high-trust and lower-risk skills are preferred for workflow composition. Search-policy weights can now be adjusted through `/api/v1/skills/search/policies` instead of editing code constants, and skill security posture can be inspected or overridden through `/api/v1/skills/{skill_id}/security-review`. Operator decisions are written to change history, can be exported through `/api/v1/skills/{skill_id}/security-history/export`, and default planning now excludes `block_or_quarantine` skills while de-prioritizing `manual_review_required` skills. The `/skills` console now includes a security overview panel, quick focus cards, and search diagnostics that show whether a candidate is eligible, cautionary, manual-review-only, or excluded from default planning, and `/operations` now links directly into those focused views via `security_focus=...`.

The `/runs` QA surface now links failed nodes and anomaly records back to the matching `skill_ref` in `/skills`, shows the current `security_verdict` inline, includes security-focus cards, adds failure presets, persists `status / security_focus / node_preset / request_id` in the URL, includes copy actions for the current audit URL and a one-line text summary, and supports a pinned-request permalink that keeps `request_id + security_focus + node_preset` while dropping transient status filters. The run-request list also exposes `Pin`, `Copy Pinned`, and `Copy Summary` quick actions per request so operators can hand off a single request without opening its detail panel first; when the request is already loaded in detail, that summary also includes the current telemetry, anomaly, and alert-delivery counts. Each request card now also shows a compact summary preview inline so operators can scan the list before copying or opening detail, and requests that include excluded or manual-review skills are highlighted directly in the list with security badges. The list also supports a shareable `flagged_only` view so teams can focus on non-eligible requests without losing the rest of the current audit context, and the header now shows dedicated clickable chips for the current request scope and flagged-request count. Current-view summaries also include the flagged-request count so copied handoff text stays aligned with the visible queue. The `/runs` header also includes inline preset buttons for `All Requests`, `Flagged Requests`, and `Flagged Failures`, so operators can jump between the most common audit queues without leaving the page. It also renders a compact “Current View” summary with the current goal and workflow name for screenshots and handoffs. The `/console` and `/operations` pages now include direct links into the most useful failed-run presets, including direct `flagged_only=1` and `flagged + failed` entrypoints, and `/operations` also exposes copy-link and dynamically generated copy-summary actions for those presets.

## Audit export and alerts

The QA surface now supports anomaly aggregation, export, and optional webhook alerts for failed client runs.

- `GET /api/v1/run-requests/export?format=csv|jsonl`
- `GET /api/v1/telemetry/events/anomalies`
- `GET /api/v1/telemetry/events/export?format=csv|jsonl&failed_only=true`
- `GET /api/v1/telemetry/alerts`
- `GET /api/v1/telemetry/alerts/export?format=csv|jsonl`
- `POST /api/v1/telemetry/alerts/{delivery_id}/replay`

Optional webhook settings:

```bash
AUDIT_ALERT_WEBHOOK_ENABLED=false
AUDIT_ALERT_WEBHOOK_URL=
AUDIT_ALERT_WEBHOOK_DESTINATIONS_JSON=[]
AUDIT_ALERT_WEBHOOK_ROUTE_RULES_JSON=[]
AUDIT_ALERT_WEBHOOK_TIMEZONE=UTC
AUDIT_ALERT_WEBHOOK_TIMEOUT_SECONDS=5
AUDIT_ALERT_WEBHOOK_MAX_RETRIES=2
AUDIT_ALERT_WEBHOOK_RETRY_BACKOFF_SECONDS=1
AUDIT_ALERT_WEBHOOK_RESPONSE_PREVIEW_CHARS=800
```

For multi-destination routing, keep `AUDIT_ALERT_WEBHOOK_ENABLED=true` and provide destination/rule JSON. Example:

```bash
AUDIT_ALERT_WEBHOOK_DESTINATIONS_JSON=[{"name":"ops","url":"https://hooks.example/ops"},{"name":"eng","url":"https://hooks.example/eng"}]
AUDIT_ALERT_WEBHOOK_ROUTE_RULES_JSON=[{"name":"default_failed","destinations":["ops"],"when":{"all":true}},{"name":"client_failures","destinations":["eng"],"when":{"client_meta_contains":{"platform":"client"}}}]
```

Route rules now support:
- `all`
- `workflow_ids`
- `run_id_prefixes`
- `failed_node_count_gte`
- `severity_any`
- `severity_at_least`
- `client_meta_contains`
- `failed_node_ids_any`
- `failed_node_error_contains`
- `quiet_hours`

`quiet_hours` expects:
- `start_hour`
- `end_hour`
- `allow_critical`

Severity is automatically derived from failed-node count and error text, and evaluated in `AUDIT_ALERT_WEBHOOK_TIMEZONE`.

Webhook alerts now record per-event delivery logs with attempt counts, final status, response code, and response preview. Multi-destination routing writes one delivery row per resolved destination, and manual replay re-sends only the selected delivery target. The `/runs` audit page shows these delivery records next to telemetry anomalies and supports manual replay for a selected delivery.

## Command planning flow

User commands can now be sent to `POST /api/v1/run-requests/`. The backend will:

- analyze the command,
- search the indexed `skills` catalog,
- compose a workflow,
- return a user-facing reply with selected skill summaries and usage guidance,
- persist a workflow record,
- wait for confirmation via `POST /api/v1/run-requests/{id}/confirm`.

Optional global AI support can be enabled with:

```bash
AI_ENABLED=true
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini
AI_API_KEY=...
```

DeepSeek V3.2 example:

```bash
AI_ENABLED=true
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-chat
AI_API_KEY=...
AI_THINKING_ENABLED=true
```

Client-side AI example:
```bash
CLIENT_AI_ENABLED=true
CLIENT_AI_BASE_URL=https://api.deepseek.com
CLIENT_AI_MODEL=deepseek-chat
CLIENT_AI_API_KEY=...
CLIENT_AI_TIMEOUT_SECONDS=30
CLIENT_AI_TEMPERATURE=0.2
CLIENT_AI_THINKING_ENABLED=true
```

Client external tool sandbox:
```bash
CLIENT_TOOL_SANDBOX_ENABLED=true
CLIENT_TOOL_ALLOWED_HOSTS=clawhub.ai,localhost,127.0.0.1,::1
CLIENT_TOOL_ALLOWED_METHODS=GET,POST
CLIENT_TOOL_ALLOWED_COMMANDS=
CLIENT_TOOL_MANIFEST_PATH=./tool-manifest.sample.json
CLIENT_TOOL_MANIFEST_REQUIRED=true
CLIENT_TOOL_MANIFEST_REQUIRE_METADATA=true
CLIENT_TOOL_MANIFEST_ALLOWED_SIGNERS=flowhub-release-bot
CLIENT_TOOL_MANIFEST_ALLOWED_FINGERPRINTS=sha256:flowhub-release-bot-2026q1
CLIENT_TOOL_MANIFEST_ALLOWED_RELEASE_BATCHES=stable-2026q1
CLIENT_TOOL_MANIFEST_CURRENT_RELEASE_BATCH=stable-2026q1
CLIENT_TOOL_MANIFEST_PREVIOUS_RELEASE_BATCHES=
CLIENT_TOOL_MANIFEST_PREVIOUS_BATCH_GRACE_DAYS=30
CLIENT_TOOL_MANIFEST_ENFORCE_EXPIRATION=true
CLIENT_TOOL_MANIFEST_REQUIRE_REVOCATION_AUDIT=true
CLIENT_TOOL_ALLOW_SENSITIVE_HEADERS=false
CLIENT_TOOL_TIMEOUT_SECONDS=20
CLIENT_TOOL_MAX_RESPONSE_BYTES=32768
```

When a node carries `inputs.external_tool`, the client runtime now executes that request through the sandbox first. Registry fetches also use the same host/method restrictions. If the registry is temporarily unavailable and no cached skill metadata exists, the client now records a degraded fetch artifact and continues with an explicit runtime hint instead of crashing immediately.

For shell tools, the safer mode is now a manifest-bound allowlist rather than a plain command-name list. Point `CLIENT_TOOL_MANIFEST_PATH` at a JSON manifest that pins each command to a repo-local path and SHA-256 digest. When `CLIENT_TOOL_MANIFEST_REQUIRE_METADATA=true`, each entry must also declare `version`, `signer`, and `published_at`. `CLIENT_TOOL_MANIFEST_ALLOWED_SIGNERS` constrains signer rotation to a known set, `CLIENT_TOOL_MANIFEST_ALLOWED_FINGERPRINTS` constrains signer fingerprints, `CLIENT_TOOL_MANIFEST_ALLOWED_RELEASE_BATCHES` constrains release batches, `CLIENT_TOOL_MANIFEST_CURRENT_RELEASE_BATCH` marks the active release window, and `CLIENT_TOOL_MANIFEST_PREVIOUS_RELEASE_BATCHES` plus `CLIENT_TOOL_MANIFEST_PREVIOUS_BATCH_GRACE_DAYS` allow a bounded grace period for the previous batch. `CLIENT_TOOL_MANIFEST_ENFORCE_EXPIRATION=true` requires a future `expires_at`, and `CLIENT_TOOL_MANIFEST_REQUIRE_REVOCATION_AUDIT=true` requires `revoked_by` and `revocation_ticket` on revoked entries. On the Windows client runtime, batch-style tools also reject multiline arguments and common shell metacharacters before execution. The sample files are:

- `client/tool-manifest.sample.json`
- `client/tool-manifest.revoked.sample.json`
- `client/sample-external-shell-plan.json`
- `client/tools/echo-tool.cmd`

Or use the DeepSeek reasoning model directly:

```bash
AI_MODEL=deepseek-reasoner
AI_THINKING_ENABLED=false
```

When enabled, the backend uses the same OpenAI-compatible gateway for:

- intake analysis
- skill/workflow planning
- user-facing reply generation

Protected generic AI endpoint:

```bash
POST /api/v1/ai/chat
```

Legacy planner-only variables are still supported:

```bash
PLANNER_AI_ENABLED=true
PLANNER_AI_BASE_URL=https://api.openai.com/v1
PLANNER_AI_MODEL=gpt-4o-mini
PLANNER_AI_API_KEY=...
```

## OpenClaw chat bridge

This repo now includes a local OpenClaw plugin at [openclaw-plugin/README.md](/mnt/f/tool/FlowHub/openclaw-plugin/README.md) so FlowHub can stay behind an OpenClaw chat agent instead of exposing a separate external form.

## QA surfaces

- `/skills`: tag library, trusted-skill filters, ranked search diagnostics, operator tag curation, change history with approval notes, and search-policy rule tuning/rollback
- `/operations`: aggregated operator change-log search and CSV/JSONL export across skills, tag definitions, and search-policy rules
- `/runs`: run request audit page for intake status, confirmation state, telemetry anomalies, webhook delivery logs, and CSV/JSONL export
- `/workflows`: workflow spec inspection and manual save path

## Client runtime samples

- `client/sample-run-plan.json`: registry fetch + client AI execution
- `client/sample-external-http-plan.json`: sandboxed local HTTP tool execution
- `client/sample-external-shell-plan.json`: manifest-bound local shell tool execution (Windows client sample)

## Docker compose

```bash
cp .env.example .env
docker compose up --build
```

`frontend` now reaches `backend` through a server-side proxy. Keep `FLOWHUB_API_KEY` as a server-only variable and do not expose it as `NEXT_PUBLIC_*`.
