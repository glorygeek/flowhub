# FlowHub Backend

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## ClawHub skill sync

Manual sync:

```bash
python scripts/sync_clawhub_skills.py
```

Force a full detail refresh:

```bash
python scripts/sync_clawhub_skills.py --full-refresh
```

API trigger:

```bash
curl -X POST \
  -H "X-API-Key: dev-flowhub-key" \
  "http://localhost:8000/api/v1/skills/sync/clawhub?full_refresh=true"
```

The backend also starts a daily APScheduler job using `CLAWHUB_SYNC_CRON` and `CLAWHUB_SYNC_TIMEZONE`.

## Command intake and confirmation

Create a planned workflow from a natural-language command:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-flowhub-key" \
  http://localhost:8000/api/v1/run-requests/ \
  -d '{
    "goal": "抓取 incident API 的最新状态并输出 markdown 简报",
    "targets": [{"type": "api", "label": "Incident API", "value": "https://example.com/api/incidents/latest"}],
    "credentials": [],
    "output_format": "markdown",
    "execution_mode": "remote",
    "user_notes": "面向客户沟通"
  }'
```

Confirm the plan and prepare the customer-facing reply payload:

```bash
curl -X POST \
  -H "X-API-Key: dev-flowhub-key" \
  http://localhost:8000/api/v1/run-requests/1/confirm
```

Enable the global AI gateway with:

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

If you want to use DeepSeek's reasoning model directly, set:

```bash
AI_MODEL=deepseek-reasoner
AI_THINKING_ENABLED=false
```

Protected backend AI chat endpoint:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-flowhub-key" \
  http://localhost:8000/api/v1/ai/chat \
  -d '{
    "messages": [
      {"role": "system", "content": "You are a concise assistant."},
      {"role": "user", "content": "Give me a one-line summary of FlowHub."}
    ]
  }'
```

The same AI gateway is now used for:

- intake actionability analysis
- skill-chain planning
- free-tier reply rewriting

Legacy planner-only variables are still accepted for compatibility:

```bash
PLANNER_AI_ENABLED=true
PLANNER_AI_BASE_URL=https://api.openai.com/v1
PLANNER_AI_MODEL=gpt-4o-mini
PLANNER_AI_API_KEY=...
```

## Test

```bash
pytest
```
