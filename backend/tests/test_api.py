from datetime import datetime, timezone

from app.core.config import Settings
from app.schemas.planner import CommunicationPreview, PlannerAssistantResponse
from app.services.ai_assistant import AIActionabilityAssessment
from app.services.ai_gateway import AIChatResult, build_chat_payload, resolve_ai_runtime
from app.services.clawhub_sync import SkillSyncResult, _build_skill_payload, _should_refresh_detail
from app.services.planner_ai import AIPlanningResult, AIWorkflowStep


def _headers():
    return {"X-API-Key": "test-api-key"}


def test_api_key_required(client):
    response = client.get("/api/v1/skills/")
    assert response.status_code == 401


def test_root_and_favicon_routes(client):
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["status"] == "ok"

    favicon = client.get("/favicon.ico")
    assert favicon.status_code == 204


def test_cors_preflight_options(client):
    response = client.options(
        "/api/v1/skills/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_skill_crud(client):
    create_payload = {
        "name": "web-scraper",
        "category": "automation",
        "description": "scrape pages",
        "tags": ["web", "scrape"],
        "input_schema": {"url": "string"},
        "output_schema": {"html": "string"},
        "execution_mode": "local",
        "risk_level": "medium",
        "status": "pending",
    }
    created = client.post("/api/v1/skills/", json=create_payload, headers=_headers())
    assert created.status_code == 201
    skill_id = created.json()["id"]

    listed = client.get("/api/v1/skills/", headers=_headers())
    assert listed.status_code == 200
    assert any(item["id"] == skill_id for item in listed.json())

    updated = client.put(
        f"/api/v1/skills/{skill_id}",
        json={"status": "approved", "risk_level": "high"},
        headers=_headers(),
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "approved"

    deleted = client.delete(f"/api/v1/skills/{skill_id}", headers=_headers())
    assert deleted.status_code == 200


def test_clawhub_sync_endpoint(client, monkeypatch):
    called: dict[str, bool] = {}

    def fake_sync(db, *, full_refresh=False, settings=None):
        _ = db
        _ = settings
        called["full_refresh"] = full_refresh
        now = datetime.now(timezone.utc)
        return SkillSyncResult(
            source="clawhub",
            total_seen=3,
            created=2,
            updated=1,
            archived=0,
            detail_requests=3,
            started_at=now,
            completed_at=now,
        )

    monkeypatch.setattr("app.api.skills.sync_clawhub_skills", fake_sync)

    response = client.post(
        "/api/v1/skills/sync/clawhub?full_refresh=true",
        headers=_headers(),
    )
    assert response.status_code == 200
    assert response.json()["source"] == "clawhub"
    assert response.json()["created"] == 2
    assert called["full_refresh"] is True


def test_new_skill_sync_fetches_detail_and_builds_quality_profile():
    assert _should_refresh_detail(existing=None, list_item={"slug": "demo"}, full_refresh=False) is True

    payload = _build_skill_payload(
        list_item={
            "slug": "stock-analysis",
            "displayName": "Stock Analysis",
            "summary": "Analyze stock markets.",
            "stats": {"stars": 140, "downloads": 26691, "installsCurrent": 208, "comments": 3},
        },
        detail={
            "skill": {
                "slug": "stock-analysis",
                "displayName": "Stock Analysis",
                "summary": "Analyze stock markets.",
                "tags": {"stock": True, "analysis": True},
            },
            "owner": {"handle": "openclaw"},
            "moderation": {"verdict": "approved"},
            "metadata": {"os": ["linux"]},
            "latestVersion": {"version": "1.2.3"},
        },
        registry_url="https://clawhub.ai",
        synced_at=datetime.now(timezone.utc),
    )

    assert "quality:trusted" in payload["tags"]
    assert "signal:official-publisher" in payload["tags"]
    assert "security:safe" in payload["tags"]
    assert payload["registry_metadata"]["quality_profile"]["tier"] == "trusted"
    assert payload["registry_metadata"]["quality_profile"]["community_validated_proxy"] is True
    assert payload["registry_metadata"]["security_profile"]["tier"] == "safe"
    assert payload["registry_metadata"]["security_profile"]["verdict"] == "safe_to_use"


def test_skill_search_endpoint_uses_remote_hits_and_reranking(client, monkeypatch):
    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "clawhub/us-stock-analysis",
            "display_name": "Us Stock Analysis",
            "category": "automation",
            "description": "Comprehensive US stock analysis for ticker requests.",
            "summary": "Analyze US stocks with fundamentals, technical analysis, and investment reports.",
            "tags": ["stock", "analysis", "report", "us", "equity"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "us-stock-analysis",
            "stats": {"stars": 140, "downloads": 26691, "installsCurrent": 208, "comments": 1},
            "is_official": True,
        },
        headers=_headers(),
    )
    assert created.status_code == 201

    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "clawhub/deepreader-skill",
            "display_name": "Deep Reader",
            "category": "automation",
            "description": "Read long documents.",
            "summary": "Read and summarize arbitrary content.",
            "tags": ["document", "summary"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "deepreader-skill",
            "stats": {"stars": 2, "downloads": 10, "installsCurrent": 1, "comments": 0},
        },
        headers=_headers(),
    )
    assert created.status_code == 201

    monkeypatch.setattr(
        "app.services.skill_search.get_settings",
        lambda: Settings(skill_search_remote_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.skill_search._fetch_remote_hits",
        lambda **kwargs: {"us-stock-analysis": 3.8, "deepreader-skill": 0.4},
    )

    response = client.get(
        "/api/v1/skills/search?q=stock%20analysis%20AAPL&limit=5",
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body[0]["skill"]["source_slug"] == "us-stock-analysis"
    assert body[0]["retrieval_source"] == "clawhub_search"
    assert body[0]["official_score"] == 3.8
    assert body[0]["quality_tier"] in {"trusted", "strong"}
    assert body[0]["quality_score"] > 0
    assert body[0]["trust_signals"]
    assert body[0]["security_tier"] in {"safe", "caution"}
    assert body[0]["security_score"] > 0
    assert body[0]["security_verdict"] in {"safe_to_use", "use_with_caution"}
    assert "stock" in body[0]["matched_terms"] or "stock" in body[0]["matched_tags"]
    assert any("ClawHub semantic search score" in item for item in body[0]["ranking_reasons"])


def test_skill_security_review_endpoint_flags_sensitive_patterns(client):
    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "clawhub/browser-cookie-runner",
            "display_name": "Browser Cookie Runner",
            "category": "developer",
            "description": "Uses browser cookies, shell commands, and API keys to execute automation.",
            "summary": "Reads browser cookie sessions and runs shell commands with API keys.",
            "tags": ["cookie", "shell", "token"],
            "execution_mode": "remote",
            "risk_level": "high",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "browser-cookie-runner",
        },
        headers=_headers(),
    )
    assert created.status_code == 201
    skill_id = created.json()["id"]
    assert created.json()["security_tier"] in {"review", "block"}

    response = client.get(f"/api/v1/skills/{skill_id}/security-review", headers=_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["security_tier"] in {"review", "block"}
    assert body["security_verdict"] in {"manual_review_required", "block_or_quarantine"}
    assert body["permission_profile"]["credential_access"] is True
    assert body["permission_profile"]["command_execution"] is True
    assert any("凭据" in item or "令牌" in item for item in body["security_flags"])


def test_skill_security_override_writeback_updates_review_and_history(client):
    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "clawhub/remote-shell-helper",
            "display_name": "Remote Shell Helper",
            "category": "developer",
            "description": "Runs shell commands against remote systems.",
            "summary": "Remote shell automation helper.",
            "tags": ["shell", "remote"],
            "execution_mode": "remote",
            "risk_level": "medium",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "remote-shell-helper",
        },
        headers=_headers(),
    )
    assert created.status_code == 201
    skill_id = created.json()["id"]

    updated = client.put(
        f"/api/v1/skills/{skill_id}/security-review",
        json={
            "decision": "block_or_quarantine",
            "change_note": "Contains remote shell access; keep out of default planning.",
            "actor": "qa-review",
        },
        headers=_headers(),
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["security_tier"] == "block"
    assert body["security_verdict"] == "block_or_quarantine"
    assert body["operator_override"]["decision"] == "block_or_quarantine"
    assert body["operator_override"]["actor"] == "qa-review"

    history = client.get(f"/api/v1/skills/{skill_id}/security-history", headers=_headers())
    assert history.status_code == 200
    entries = history.json()
    assert entries
    assert entries[0]["action"] == "update_skill_security_override"
    assert entries[0]["actor"] == "qa-review"

    exported = client.get(f"/api/v1/skills/{skill_id}/security-history/export?format=csv", headers=_headers())
    assert exported.status_code == 200
    assert "update_skill_security_override" in exported.text


def test_skill_resolve_endpoint_matches_exact_name_and_source_slug(client):
    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "clawhub/us-stock-safe-resolve",
            "display_name": "US Stock Safe Resolve",
            "category": "automation",
            "description": "Analyze US stocks and return markdown briefs.",
            "summary": "Stock analysis helper.",
            "tags": ["stock", "analysis", "report", "equity"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "us-stock-safe-resolve",
        },
        headers=_headers(),
    )
    assert created.status_code == 201

    response = client.get(
        "/api/v1/skills/resolve?refs=clawhub/us-stock-safe-resolve,us-stock-safe-resolve,output.export",
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["requested_ref"] for item in body] == [
        "clawhub/us-stock-safe-resolve",
        "us-stock-safe-resolve",
        "output.export",
    ]
    assert body[0]["matched_by"] == "name"
    assert body[0]["skill"]["name"] == "clawhub/us-stock-safe-resolve"
    assert body[1]["matched_by"] == "source_slug"
    assert body[1]["skill"]["source_slug"] == "us-stock-safe-resolve"
    assert body[2]["skill"] is None


def test_run_request_excludes_blocked_skill_overrides_from_default_planning(client):
    blocked = client.post(
        "/api/v1/skills/",
        json={
            "name": "clawhub/us-stock-risky",
            "display_name": "US Stock Risky",
            "category": "automation",
            "description": "Analyze US stocks with shell access and browser cookies.",
            "summary": "Stock analysis helper with elevated behaviors.",
            "tags": ["stock", "analysis", "shell", "cookie", "equity"],
            "execution_mode": "remote",
            "risk_level": "high",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "us-stock-risky",
            "stats": {"stars": 200, "downloads": 30000, "installsCurrent": 300, "comments": 3},
            "is_official": True,
        },
        headers=_headers(),
    )
    assert blocked.status_code == 201
    blocked_id = blocked.json()["id"]
    override = client.put(
        f"/api/v1/skills/{blocked_id}/security-review",
        json={
            "decision": "block_or_quarantine",
            "change_note": "Blocked by operator review.",
            "actor": "qa-review",
        },
        headers=_headers(),
    )
    assert override.status_code == 200

    safe = client.post(
        "/api/v1/skills/",
        json={
            "name": "clawhub/us-stock-safe",
            "display_name": "US Stock Safe",
            "category": "automation",
            "description": "Analyze US stocks and return markdown briefs.",
            "summary": "Stock analysis helper.",
            "tags": ["stock", "analysis", "report", "equity"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "us-stock-safe",
            "stats": {"stars": 20, "downloads": 1000, "installsCurrent": 20, "comments": 1},
        },
        headers=_headers(),
    )
    assert safe.status_code == 201

    response = client.post(
        "/api/v1/run-requests/",
        json={
            "goal": "Analyze AAPL and return a markdown investment brief",
            "targets": [{"type": "text", "label": "ticker", "value": "AAPL"}],
            "credentials": [],
            "output_format": "markdown",
            "execution_mode": "remote",
            "user_notes": "Prefer default safe workflow.",
        },
        headers=_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["selected_skills"]
    assert all(item["name"] != "clawhub/us-stock-risky" for item in body["selected_skills"])
    assert all(item["security_verdict"] != "block_or_quarantine" for item in body["selected_skills"])


def test_skill_search_prefers_higher_trust_when_relevance_is_similar(client, monkeypatch):
    for payload in [
        {
            "name": "clawhub/trusted-stock-skill",
            "display_name": "Trusted Stock Skill",
            "category": "automation",
            "description": "Analyze stock market data and produce investor briefs.",
            "summary": "Analyze stock market data and produce investor briefs.",
            "tags": ["stock", "analysis", "report"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "trusted-stock-skill",
            "is_official": True,
            "stats": {"stars": 120, "downloads": 12000, "installsCurrent": 88, "comments": 3},
        },
        {
            "name": "clawhub/weak-stock-skill",
            "display_name": "Weak Stock Skill",
            "category": "automation",
            "description": "Analyze stock market data and produce investor briefs.",
            "summary": "Analyze stock market data and produce investor briefs.",
            "tags": ["stock", "analysis", "report"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "weak-stock-skill",
            "stats": {"stars": 1, "downloads": 4, "installsCurrent": 0, "comments": 0},
        },
    ]:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    monkeypatch.setattr(
        "app.services.skill_search.get_settings",
        lambda: Settings(skill_search_remote_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.skill_search._fetch_remote_hits",
        lambda **kwargs: {"trusted-stock-skill": 2.0, "weak-stock-skill": 2.0},
    )

    response = client.get(
        "/api/v1/skills/search?q=stock%20analysis%20brief&limit=5",
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body[0]["skill"]["source_slug"] == "trusted-stock-skill"


def test_skill_tag_library_indexes_and_filters_skills(client):
    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "clawhub/a-share-tagged-skill",
            "display_name": "A Share Tagged Skill",
            "category": "automation",
            "description": "Analyze China A-share opportunities.",
            "summary": "A-share analysis skill.",
            "tags": ["a股", "analysis", "swing"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "a-share-tagged-skill",
            "stats": {"stars": 80, "downloads": 3200, "installsCurrent": 18, "comments": 1},
            "is_official": True,
        },
        headers=_headers(),
    )
    assert created.status_code == 201

    tags_response = client.get("/api/v1/skills/tags", headers=_headers())
    assert tags_response.status_code == 200
    tags = tags_response.json()
    tag_names = {item["name"] for item in tags}
    assert "a股" in tag_names
    assert "source:clawhub" in tag_names
    assert "category:automation" in tag_names
    assert "signal:official" in tag_names

    filtered = client.get("/api/v1/skills/?tags=a股,source:clawhub", headers=_headers())
    assert filtered.status_code == 200
    body = filtered.json()
    assert len(body) == 1
    assert body[0]["name"] == "clawhub/a-share-tagged-skill"


def test_skill_tag_curation_preserves_operator_tags_and_respects_active_flag(client):
    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "manual/curated-skill",
            "display_name": "Curated Skill",
            "category": "automation",
            "description": "Summarize datasets and generate markdown updates.",
            "summary": "Curated skill for operator tagging.",
            "tags": ["dataset", "summary"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
        },
        headers=_headers(),
    )
    assert created.status_code == 201
    skill_id = created.json()["id"]

    initial_tags = client.get(f"/api/v1/skills/{skill_id}/tags", headers=_headers())
    assert initial_tags.status_code == 200
    assert any(item["name"] == "category:automation" for item in initial_tags.json())

    curated = client.put(
        f"/api/v1/skills/{skill_id}/tags",
        json={"tag_names": ["desk:priority", "domain:china_equity"]},
        headers=_headers(),
    )
    assert curated.status_code == 200
    curated_body = curated.json()
    assert any(item["name"] == "desk:priority" and item["link_source"] == "operator" for item in curated_body)
    assert any(item["name"] == "domain:china_equity" and item["link_source"] == "operator" for item in curated_body)

    updated = client.put(
        f"/api/v1/skills/{skill_id}",
        json={"description": "Updated description after manual curation."},
        headers=_headers(),
    )
    assert updated.status_code == 200

    after_update = client.get(f"/api/v1/skills/{skill_id}/tags", headers=_headers())
    assert after_update.status_code == 200
    assert any(item["name"] == "desk:priority" and item["link_source"] == "operator" for item in after_update.json())

    tag_library = client.get("/api/v1/skills/tags?q=desk:priority", headers=_headers())
    assert tag_library.status_code == 200
    tag_id = tag_library.json()[0]["id"]

    disabled = client.put(
        f"/api/v1/skills/tags/{tag_id}",
        json={"active": False, "description": "Temporarily disabled by operator."},
        headers=_headers(),
    )
    assert disabled.status_code == 200
    assert disabled.json()["active"] is False

    filtered = client.get("/api/v1/skills/?tags=desk:priority", headers=_headers())
    assert filtered.status_code == 200
    assert filtered.json() == []


def test_skill_search_prefers_a_share_skills_for_china_market_queries(client, monkeypatch):
    for payload in [
        {
            "name": "clawhub/a-stock-monitor",
            "display_name": "A Stock Monitor",
            "category": "automation",
            "description": "Analyze China A-share行情、板块和交易信号。",
            "summary": "A-share analysis for SH/SZ tickers.",
            "tags": ["a股", "china", "stock", "analysis", "akshare"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "a-stock-monitor",
            "stats": {"stars": 48, "downloads": 6800, "installsCurrent": 45, "comments": 2},
        },
        {
            "name": "clawhub/us-stock-analysis-market",
            "display_name": "US Stock Analysis",
            "category": "automation",
            "description": "Analyze US equities and return investor briefs.",
            "summary": "US stock analysis for NASDAQ and NYSE tickers.",
            "tags": ["us", "stock", "analysis", "equity"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "us-stock-analysis-market",
            "stats": {"stars": 80, "downloads": 12000, "installsCurrent": 88, "comments": 2},
        },
    ]:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    monkeypatch.setattr(
        "app.services.skill_search.get_settings",
        lambda: Settings(skill_search_remote_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.skill_search._fetch_remote_hits",
        lambda **kwargs: {"a-stock-monitor": 3.2, "us-stock-analysis-market": 4.0},
    )

    response = client.get(
        "/api/v1/skills/search?q=%E5%88%86%E6%9E%90600519%E5%92%8C300750%E7%9A%84A%E8%82%A1%E8%B5%B0%E5%8A%BF&limit=5",
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body[0]["skill"]["source_slug"] == "a-stock-monitor"
    assert any("China A-share" in item for item in body[0]["ranking_reasons"])


def test_skill_search_whitelists_api_collection_requests(client, monkeypatch):
    for payload in [
        {
            "name": "clawhub/api-fetch-pro",
            "display_name": "API Fetch Pro",
            "category": "web",
            "description": "Fetch data from REST APIs and export structured JSON or CSV.",
            "summary": "API data collection and export skill.",
            "tags": ["api", "fetch", "json", "csv"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "api-fetch-pro",
            "stats": {"stars": 24, "downloads": 1800, "installsCurrent": 12, "comments": 1},
        },
        {
            "name": "clawhub/stock-noise-signal",
            "display_name": "Stock Noise Signal",
            "category": "automation",
            "description": "Analyze US stocks and return trading signals.",
            "summary": "US stock signal analysis.",
            "tags": ["stock", "analysis", "signal"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "stock-noise-signal",
            "stats": {"stars": 110, "downloads": 22000, "installsCurrent": 160, "comments": 4},
        },
    ]:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    monkeypatch.setattr(
        "app.services.skill_search.get_settings",
        lambda: Settings(skill_search_remote_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.skill_search._fetch_remote_hits",
        lambda **kwargs: {"api-fetch-pro": 1.6, "stock-noise-signal": 4.4},
    )

    response = client.get(
        "/api/v1/skills/search?q=fetch%20this%20API%20and%20export%20json&limit=5",
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body[0]["skill"]["source_slug"] == "api-fetch-pro"
    assert any("API/data collection intent" in item for item in body[0]["ranking_reasons"])


def test_skill_search_whitelists_customer_reply_requests(client, monkeypatch):
    for payload in [
        {
            "name": "clawhub/customer-reply-writer",
            "display_name": "Customer Reply Writer",
            "category": "analysis",
            "description": "Draft customer-facing markdown replies from incidents and summaries.",
            "summary": "Customer-facing markdown reply generator.",
            "tags": ["customer", "reply", "markdown", "summary"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "customer-reply-writer",
            "stats": {"stars": 18, "downloads": 900, "installsCurrent": 8, "comments": 1},
        },
        {
            "name": "clawhub/crypto-noise-agent",
            "display_name": "Crypto Noise Agent",
            "category": "automation",
            "description": "Aggressive crypto trading signal generation.",
            "summary": "Crypto trading signal automation.",
            "tags": ["crypto", "signal", "momentum"],
            "execution_mode": "remote",
            "risk_level": "medium",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "crypto-noise-agent",
            "stats": {"stars": 95, "downloads": 17000, "installsCurrent": 120, "comments": 3},
        },
    ]:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    monkeypatch.setattr(
        "app.services.skill_search.get_settings",
        lambda: Settings(skill_search_remote_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.skill_search._fetch_remote_hits",
        lambda **kwargs: {"customer-reply-writer": 1.2, "crypto-noise-agent": 4.8},
    )

    response = client.get(
        "/api/v1/skills/search?q=summarize%20this%20incident%20and%20draft%20a%20customer-facing%20markdown%20reply&limit=5",
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body[0]["skill"]["source_slug"] == "customer-reply-writer"
    assert any("customer-facing reply intent" in item for item in body[0]["ranking_reasons"])


def test_search_policy_rules_can_be_listed_and_updated(client, monkeypatch):
    for payload in [
        {
            "name": "clawhub/api-fetch-policy-test",
            "display_name": "API Fetch Policy Test",
            "category": "web",
            "description": "Fetch data from REST APIs and export JSON.",
            "summary": "API collection skill.",
            "tags": ["api", "fetch", "json"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "api-fetch-policy-test",
            "stats": {"stars": 14, "downloads": 1200, "installsCurrent": 6, "comments": 1},
        },
        {
            "name": "clawhub/stock-policy-noise",
            "display_name": "Stock Policy Noise",
            "category": "automation",
            "description": "Analyze US stocks and return signals.",
            "summary": "US stock signal analysis.",
            "tags": ["stock", "analysis", "signal"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "stock-policy-noise",
            "stats": {"stars": 108, "downloads": 20500, "installsCurrent": 144, "comments": 4},
        },
    ]:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    monkeypatch.setattr(
        "app.services.skill_search.get_settings",
        lambda: Settings(skill_search_remote_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.skill_search._fetch_remote_hits",
        lambda **kwargs: {"api-fetch-policy-test": 1.2, "stock-policy-noise": 4.9},
    )

    listed = client.get("/api/v1/skills/search/policies", headers=_headers())
    assert listed.status_code == 200
    body = listed.json()
    assert any(item["name"] == "api_fetch_collector_boost" for item in body)
    assert any(item["name"] == "api_fetch_market_penalty" for item in body)

    baseline = client.get(
        "/api/v1/skills/search?q=fetch%20this%20API%20and%20export%20json&limit=5",
        headers=_headers(),
    )
    assert baseline.status_code == 200
    assert baseline.json()[0]["skill"]["source_slug"] == "api-fetch-policy-test"

    collector_boost_rule = next(item for item in body if item["name"] == "api_fetch_collector_boost")
    market_penalty_rule = next(item for item in body if item["name"] == "api_fetch_market_penalty")
    for rule_id in (collector_boost_rule["id"], market_penalty_rule["id"]):
        updated = client.put(
            f"/api/v1/skills/search/policies/{rule_id}",
            json={"active": False},
            headers=_headers(),
        )
        assert updated.status_code == 200
        assert updated.json()["active"] is False

    reranked = client.get(
        "/api/v1/skills/search?q=fetch%20this%20API%20and%20export%20json&limit=5",
        headers=_headers(),
    )
    assert reranked.status_code == 200
    assert reranked.json()[0]["skill"]["source_slug"] == "stock-policy-noise"


def test_skill_tag_history_records_note_and_state(client):
    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "manual/history-skill",
            "display_name": "History Skill",
            "category": "analysis",
            "description": "Skill used for tag history tests.",
            "summary": "History test skill.",
            "status": "approved",
            "risk_level": "low"
        },
        headers=_headers(),
    )
    assert created.status_code == 201
    skill_id = created.json()["id"]

    assigned = client.put(
        f"/api/v1/skills/{skill_id}/tags",
        json={
            "tag_names": ["desk:priority", "domain:china_equity"],
            "change_note": "Approved for China equity desk coverage.",
            "actor": "qa-ops"
        },
        headers=_headers(),
    )
    assert assigned.status_code == 200

    history = client.get(f"/api/v1/skills/{skill_id}/tag-history", headers=_headers())
    assert history.status_code == 200
    body = history.json()
    assert len(body) == 1
    assert body[0]["action"] == "replace_operator_tags"
    assert body[0]["actor"] == "qa-ops"
    assert body[0]["note"] == "Approved for China equity desk coverage."
    assert body[0]["before_state"] == {"tag_names": []}
    assert sorted(body[0]["after_state"]["tag_names"]) == ["desk:priority", "domain:china_equity"]

    filtered = client.get(
        f"/api/v1/skills/{skill_id}/tag-history?actor=qa-ops&note_q=China%20equity",
        headers=_headers(),
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1

    exported = client.get(
        f"/api/v1/skills/{skill_id}/tag-history/export?format=csv&actor=qa-ops",
        headers=_headers(),
    )
    assert exported.status_code == 200
    assert "qa-ops" in exported.text
    assert "Approved for China equity desk coverage." in exported.text


def test_search_policy_history_records_note_and_state(client):
    listed = client.get("/api/v1/skills/search/policies", headers=_headers())
    assert listed.status_code == 200
    rule = next(item for item in listed.json() if item["name"] == "api_fetch_collector_boost")

    updated = client.put(
        f"/api/v1/skills/search/policies/{rule['id']}",
        json={
            "score_delta": 15,
            "priority": 90,
            "change_note": "Raised collector boost after API retrieval QA review.",
            "actor": "policy-admin"
        },
        headers=_headers(),
    )
    assert updated.status_code == 200
    assert updated.json()["score_delta"] == 15
    assert updated.json()["priority"] == 90

    history = client.get(
        f"/api/v1/skills/search/policies/{rule['id']}/history",
        headers=_headers(),
    )
    assert history.status_code == 200
    body = history.json()
    latest = body[0]
    assert latest["action"] == "update_search_policy_rule"
    assert latest["actor"] == "policy-admin"
    assert latest["note"] == "Raised collector boost after API retrieval QA review."
    assert latest["before_state"]["score_delta"] == rule["score_delta"]
    assert latest["after_state"]["score_delta"] == 15
    assert latest["before_state"]["priority"] == rule["priority"]
    assert latest["after_state"]["priority"] == 90

    rolled_back = client.post(
        f"/api/v1/skills/search/policies/{rule['id']}/rollback/{latest['id']}",
        json={
            "change_note": "Rollback after QA regression.",
            "actor": "policy-admin"
        },
        headers=_headers(),
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["score_delta"] == rule["score_delta"]
    assert rolled_back.json()["priority"] == rule["priority"]

    history_after = client.get(
        f"/api/v1/skills/search/policies/{rule['id']}/history",
        headers=_headers(),
    )
    assert history_after.status_code == 200
    newest = history_after.json()[0]
    assert newest["action"] == "rollback_search_policy_rule"
    assert newest["note"] == "Rollback after QA regression."

    exported = client.get(
        f"/api/v1/skills/search/policies/{rule['id']}/history/export?format=jsonl&actor=policy-admin",
        headers=_headers(),
    )
    assert exported.status_code == 200
    assert "policy-admin" in exported.text
    assert "Rollback after QA regression." in exported.text


def test_global_operator_change_log_listing_and_export(client):
    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "manual/global-history-skill",
            "display_name": "Global History Skill",
            "category": "analysis",
            "description": "Skill used for aggregated operator history tests.",
            "summary": "Global history test skill.",
            "status": "approved",
            "risk_level": "low",
        },
        headers=_headers(),
    )
    assert created.status_code == 201
    skill_id = created.json()["id"]

    assigned = client.put(
        f"/api/v1/skills/{skill_id}/tags",
        json={
            "tag_names": ["desk:priority"],
            "change_note": "Tagged for desk escalation.",
            "actor": "ops-reviewer",
        },
        headers=_headers(),
    )
    assert assigned.status_code == 200

    listed = client.get("/api/v1/skills/search/policies", headers=_headers())
    assert listed.status_code == 200
    rule = next(item for item in listed.json() if item["name"] == "api_fetch_collector_boost")

    updated = client.put(
        f"/api/v1/skills/search/policies/{rule['id']}",
        json={
            "score_delta": 13,
            "change_note": "Raised after operator review.",
            "actor": "ops-reviewer",
        },
        headers=_headers(),
    )
    assert updated.status_code == 200

    aggregate = client.get(
        "/api/v1/skills/change-logs?actor=ops-reviewer&limit=10",
        headers=_headers(),
    )
    assert aggregate.status_code == 200
    body = aggregate.json()
    assert len(body) >= 2
    assert {item["entity_type"] for item in body} >= {"skill_operator_tags", "search_policy_rule"}

    filtered = client.get(
        "/api/v1/skills/change-logs?entity_type=search_policy_rule&action=update_search_policy_rule&note_q=operator%20review",
        headers=_headers(),
    )
    assert filtered.status_code == 200
    filtered_body = filtered.json()
    assert len(filtered_body) == 1
    assert filtered_body[0]["entity_type"] == "search_policy_rule"
    assert filtered_body[0]["action"] == "update_search_policy_rule"

    exported = client.get(
        "/api/v1/skills/change-logs/export?format=csv&actor=ops-reviewer",
        headers=_headers(),
    )
    assert exported.status_code == 200
    assert "ops-reviewer" in exported.text
    assert "Tagged for desk escalation." in exported.text


def test_run_request_prefers_a_share_skill_for_china_market_request(client, monkeypatch):
    for payload in [
        {
            "name": "clawhub/a-stock-monitor-plan",
            "display_name": "A Stock Monitor",
            "category": "automation",
            "description": "Analyze China A-share行情、板块和交易信号。",
            "summary": "A-share analysis for SH/SZ tickers.",
            "tags": ["a股", "china", "stock", "analysis", "report"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "a-stock-monitor-plan",
            "stats": {"stars": 42, "downloads": 5400, "installsCurrent": 32, "comments": 2},
        },
        {
            "name": "clawhub/us-stock-analysis-plan",
            "display_name": "US Stock Analysis",
            "category": "automation",
            "description": "Analyze US equities and return investor briefs.",
            "summary": "US stock analysis for NASDAQ and NYSE tickers.",
            "tags": ["us", "stock", "analysis", "report"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "us-stock-analysis-plan",
            "stats": {"stars": 90, "downloads": 18800, "installsCurrent": 110, "comments": 3},
        },
    ]:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    monkeypatch.setattr(
        "app.services.skill_search.get_settings",
        lambda: Settings(skill_search_remote_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.skill_search._fetch_remote_hits",
        lambda **kwargs: {"a-stock-monitor-plan": 3.4, "us-stock-analysis-plan": 4.1},
    )

    response = client.post(
        "/api/v1/run-requests/",
        json={
            "goal": "分析 600519 和 300750 的A股走势，并给我一份 markdown 简报",
            "targets": [{"type": "text", "label": "ticker", "value": "600519,300750"}],
            "credentials": [],
            "output_format": "markdown",
            "execution_mode": "remote",
            "user_notes": "关注A股板块轮动和交易信号。",
        },
        headers=_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["selected_skills"][0]["name"] == "clawhub/a-stock-monitor-plan"
    assert body["workflow_spec"]["nodes"][0]["skill_ref"] == "clawhub/a-stock-monitor-plan"
    assert body["selected_skills"][0]["quality_tier"] in {"trusted", "strong"}
    assert body["selected_skills"][0]["trust_signals"]
    assert any("single indexed skill" in item.lower() or "selected" in item.lower() for item in body["decision_log"])


def test_recipe_and_workflow_crud(client):
    recipe_payload = {
        "name": "ingestion-pipeline",
        "scenario": "ingestion",
        "description": "pipeline template",
        "tags": ["etl"],
        "node_skeleton": [
            {"id": "n1", "skill_category": "extract", "config": {}},
            {"id": "n2", "skill_category": "load", "config": {}},
        ],
        "edges": [{"from_node": "n1", "to_node": "n2"}],
        "param_mappings": {},
        "recommended_skill_categories": ["extract", "load"],
        "risk_level": "medium",
        "status": "pending",
    }
    recipe_created = client.post("/api/v1/recipes/", json=recipe_payload, headers=_headers())
    assert recipe_created.status_code == 201
    recipe_id = recipe_created.json()["id"]

    recipe_updated = client.put(
        f"/api/v1/recipes/{recipe_id}",
        json={"status": "approved"},
        headers=_headers(),
    )
    assert recipe_updated.status_code == 200
    assert recipe_updated.json()["status"] == "approved"

    workflow_payload = {
        "name": "ingestion-flow",
        "description": "workflow from recipe",
        "inputs": {"source": "demo"},
        "nodes": [
            {"id": "n1", "name": "extract", "skill_ref": "extractor.run", "inputs": {}},
            {"id": "n2", "name": "load", "skill_ref": "loader.run", "inputs": {}},
        ],
        "edges": [{"from_node": "n1", "to_node": "n2"}],
        "outputs": {"result": "ok"},
        "source_recipe_id": recipe_id,
        "risk_level": "medium",
        "status": "pending",
        "retry_policy": {"max_retries": 1},
        "confirm_points": ["n1"],
        "planner_decision_log": ["manual"],
    }
    workflow_created = client.post(
        "/api/v1/workflows/",
        json=workflow_payload,
        headers=_headers(),
    )
    assert workflow_created.status_code == 201
    workflow_id = workflow_created.json()["id"]

    workflow_get = client.get(f"/api/v1/workflows/{workflow_id}", headers=_headers())
    assert workflow_get.status_code == 200
    assert workflow_get.json()["name"] == "ingestion-flow"

    workflow_delete = client.delete(f"/api/v1/workflows/{workflow_id}", headers=_headers())
    assert workflow_delete.status_code == 200

    recipe_delete = client.delete(f"/api/v1/recipes/{recipe_id}", headers=_headers())
    assert recipe_delete.status_code == 200


def test_planner_requires_request_text(client):
    response = client.post(
        "/api/v1/planner/plan",
        json={"request_text": "", "client_capabilities": {}},
        headers=_headers(),
    )
    assert response.status_code == 422


def test_planner_returns_usage_guidance_for_non_actionable_message(client):
    response = client.post(
        "/api/v1/planner/plan",
        json={"request_text": "hello", "client_capabilities": {}},
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["actionable"] is False
    assert body["workflow_spec"] is None
    assert body["estimated_risk"] is None
    assert body["assistant_response"]["template_key"] == "free_usage_guidance"
    assert body["communication_preview"]["template_key"] == "free_usage_guidance"
    assert body["communication_preview"]["status"] == "needs_clarification"
    assert body["assistant_response"]["headline"]
    assert body["assistant_response"]["reply_text"]
    assert isinstance(body["assistant_response"]["usage_steps"], list)


def test_ai_chat_endpoint_uses_generic_gateway(client, monkeypatch):
    monkeypatch.setattr("app.api.ai.can_use_ai", lambda settings: True)
    monkeypatch.setattr(
        "app.api.ai.request_ai_chat",
        lambda **kwargs: AIChatResult(
            provider="deepseek",
            model="demo-model",
            content="hello from ai",
            reasoning_content="thinking trace",
            raw_response={"usage": {"prompt_tokens": 10, "completion_tokens": 3}},
        ),
    )

    response = client.post(
        "/api/v1/ai/chat",
        json={
            "messages": [
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user", "content": "Say hello"},
            ]
        },
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["model"] == "demo-model"
    assert body["content"] == "hello from ai"
    assert body["provider"] == "deepseek"
    assert body["reasoning_content"] == "thinking trace"
    assert body["usage"]["prompt_tokens"] == 10


def test_ai_gateway_builds_deepseek_v32_thinking_payload():
    settings = Settings(
        ai_enabled=True,
        ai_base_url="https://api.deepseek.com",
        ai_model="deepseek-chat",
        ai_api_key="test-key",
        ai_thinking_enabled=True,
    )
    runtime = resolve_ai_runtime(settings)
    payload = build_chat_payload(
        runtime=runtime,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert payload["model"] == "deepseek-chat"
    assert payload["thinking"] == {"type": "enabled"}


def test_planner_can_use_ai_actionability_analysis(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.planner_engine.assess_request_actionability_with_ai",
        lambda **kwargs: AIActionabilityAssessment(
            actionable=True,
            reason="The message asks the system to proceed with a concrete task.",
            missing_information=[],
        ),
    )

    response = client.post(
        "/api/v1/planner/plan",
        json={"request_text": "hello", "client_capabilities": {}},
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["actionable"] is True
    assert body["workflow_spec"] is not None
    assert any("AI analyzed the intake" in item for item in body["decision_log"])


def test_planner_and_telemetry_chain(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.planner_engine.select_skill_candidates",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "app.services.planner_engine.assess_request_actionability_with_ai",
        lambda **kwargs: AIActionabilityAssessment(
            actionable=True,
            reason="Recipe telemetry test should proceed as actionable.",
            missing_information=[],
        ),
    )

    recipe_payload = {
        "name": "basic-analysis",
        "scenario": "analysis",
        "tags": ["analyze", "summary"],
        "node_skeleton": [
            {"id": "n1", "skill_category": "analysis", "config": {}},
            {"id": "n2", "skill_category": "report", "config": {}},
        ],
        "edges": [{"from_node": "n1", "to_node": "n2"}],
        "risk_level": "low",
        "status": "approved",
    }
    recipe_resp = client.post("/api/v1/recipes/", json=recipe_payload, headers=_headers())
    assert recipe_resp.status_code == 201

    plan_payload = {
        "request_text": "analyze this incident report and return a summary",
        "client_capabilities": {"supports_playwright": False},
        "risk_tolerance": "medium",
    }
    plan_resp = client.post("/api/v1/planner/plan", json=plan_payload, headers=_headers())
    assert plan_resp.status_code == 200
    body = plan_resp.json()
    assert "workflow_spec" in body
    assert "assistant_response" in body
    assert len(body["workflow_spec"]["nodes"]) >= 1
    assert body["workflow_spec"]["nodes"][0]["name"] == "analysis"
    assert body["workflow_spec"]["nodes"][0]["skill_ref"] == "analysis.execute"

    telemetry_payload = {
        "workflow_id": None,
        "run_id": "run-001",
        "node_results": [
            {
                "node_id": "n1",
                "status": "success",
                "output": {"ok": True},
                "retry_count": 0,
            }
        ],
        "summary": {"success": 1, "failed": 0},
        "client_meta": {"platform": "test"},
    }
    telemetry_resp = client.post(
        "/api/v1/telemetry/events",
        json=telemetry_payload,
        headers=_headers(),
    )
    assert telemetry_resp.status_code == 200
    assert telemetry_resp.json()["accepted"] is True


def test_planner_uses_ai_skill_selection_when_available(client, monkeypatch):
    skill_payloads = [
        {
            "name": "clawhub/web-fetcher-ai",
            "display_name": "Web Fetcher",
            "category": "web",
            "description": "fetch report pages from urls",
            "summary": "fetch report pages from urls",
            "tags": ["fetch", "web", "report"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
        },
        {
            "name": "clawhub/report-summarizer-ai",
            "display_name": "Report Summarizer",
            "category": "analysis",
            "description": "summarize reports into markdown",
            "summary": "summarize reports into markdown",
            "tags": ["summary", "markdown", "report"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
        },
    ]
    for payload in skill_payloads:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    def fake_ai(*, goal, targets, output_format, execution_mode, candidates, settings):
        _ = goal
        _ = targets
        _ = output_format
        _ = execution_mode
        _ = candidates
        _ = settings
        return AIPlanningResult(
            workflow_name="AI Incident Plan",
            summary="AI selected a fetch step followed by report summarization.",
            selected_skill_slugs=["web-fetcher-ai", "report-summarizer-ai"],
            usage_steps=["Provide the report URL.", "Confirm the markdown output."],
            skill_reasons={
                "web-fetcher-ai": "Needed to collect the source report.",
                "report-summarizer-ai": "Needed to produce the final markdown summary.",
            },
            workflow_steps=[
                AIWorkflowStep(
                    skill_slug="web-fetcher-ai",
                    name="Fetch source report",
                    inputs={"mode": "snapshot"},
                ),
                AIWorkflowStep(skill_slug="report-summarizer-ai", name="Summarize report", inputs={}),
            ],
        )

    monkeypatch.setattr("app.services.planner_engine.plan_skill_chain_with_ai", fake_ai)

    response = client.post(
        "/api/v1/planner/plan",
        json={"request_text": "fetch this report and summarize it in markdown"},
        headers=_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workflow_spec"]["name"] == "AI Incident Plan"
    assert body["workflow_spec"]["nodes"][0]["name"] == "Fetch source report"
    assert body["assistant_response"]["template_key"] == "free_minimal_combo_plan"
    assert body["selected_skills"][0]["display_name"] == "Web Fetcher"
    assert "最小可行方案" in body["assistant_response"]["headline"]
    assert any("Planner AI selected" in item for item in body["decision_log"])


def test_run_request_returns_guidance_without_persisting_for_non_actionable_message(client):
    before = client.get("/api/v1/run-requests/", headers=_headers())
    assert before.status_code == 200
    before_count = len(before.json())

    payload = {
        "goal": "你好",
        "targets": [],
        "credentials": [],
        "output_format": "markdown",
        "execution_mode": "remote",
        "user_notes": "",
    }
    created = client.post("/api/v1/run-requests/", json=payload, headers=_headers())
    assert created.status_code == 200

    body = created.json()
    assert body["actionable"] is False
    assert body["request"] is None
    assert body["workflow_spec"] is None
    assert body["assistant_response"]["template_key"] == "free_usage_guidance"
    assert body["communication_preview"]["status"] == "needs_clarification"

    listed = client.get("/api/v1/run-requests/", headers=_headers())
    assert listed.status_code == 200
    assert len(listed.json()) == before_count


def test_run_request_prefers_single_skill_when_one_skill_can_cover_request(client):
    skill_payloads = [
        {
            "name": "clawhub/stock-analyst-free",
            "display_name": "Stock Analyst",
            "category": "automation",
            "description": "Comprehensive stock analysis with fundamentals, technical analysis, and investment report generation.",
            "summary": "Comprehensive stock analysis with report generation for US stocks.",
            "tags": ["stock", "analysis", "report", "fundamental", "technical"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
        },
        {
            "name": "clawhub/market-news-free",
            "display_name": "Market News",
            "category": "web",
            "description": "Collect market-moving equity news.",
            "summary": "Collect equity market news.",
            "tags": ["market", "news", "equity"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
        },
    ]
    for payload in skill_payloads:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    payload = {
        "goal": "Analyze AAPL and return a markdown investment brief",
        "targets": [{"type": "text", "label": "ticker", "value": "AAPL"}],
        "credentials": [],
        "output_format": "markdown",
        "execution_mode": "remote",
        "user_notes": "Focus on trend and valuation.",
    }
    created = client.post("/api/v1/run-requests/", json=payload, headers=_headers())
    assert created.status_code == 201

    body = created.json()
    assert body["actionable"] is True
    assert body["assistant_response"]["template_key"] == "free_single_skill_plan"
    assert body["communication_preview"]["template_key"] == "free_single_skill_plan"
    assert len(body["selected_skills"]) == 1
    assert "stock" in body["selected_skills"][0]["display_name"].lower()
    assert body["selected_skills"][0]["quality_tier"]
    assert isinstance(body["selected_skills"][0]["trust_signals"], list)
    assert "stock" in body["workflow_spec"]["nodes"][0]["skill_ref"].lower()
    assert body["workflow_spec"]["nodes"][-1]["skill_ref"] == "output.export"
    assert any("single indexed skill" in item.lower() for item in body["decision_log"])


def test_run_request_uses_quick_search_to_keep_stock_request_on_domain(client, monkeypatch):
    for payload in [
        {
            "name": "clawhub/us-stock-analysis-quick",
            "display_name": "Us Stock Analysis",
            "category": "automation",
            "description": "Comprehensive US stock analysis with fundamentals, technical analysis, and report generation.",
            "summary": "Comprehensive US stock analysis with investment report generation.",
            "tags": ["stock", "analysis", "report", "fundamental", "technical", "equity"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "us-stock-analysis-quick",
            "stats": {"stars": 140, "downloads": 26691, "installsCurrent": 208, "comments": 1},
            "is_official": True,
        },
        {
            "name": "clawhub/deepreader-skill-quick",
            "display_name": "Deep Reader",
            "category": "automation",
            "description": "Read long documents and summarize them.",
            "summary": "Read documents and return summaries.",
            "tags": ["document", "summary"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
            "source": "clawhub",
            "source_slug": "deepreader-skill-quick",
            "stats": {"stars": 1, "downloads": 5, "installsCurrent": 1, "comments": 0},
        },
    ]:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    monkeypatch.setattr(
        "app.services.skill_search.get_settings",
        lambda: Settings(skill_search_remote_enabled=True),
    )
    monkeypatch.setattr(
        "app.services.skill_search._fetch_remote_hits",
        lambda **kwargs: {"us-stock-analysis-quick": 4.2, "deepreader-skill-quick": 0.2},
    )

    response = client.post(
        "/api/v1/run-requests/",
        json={
            "goal": "Analyze AAPL and return a markdown investment brief",
            "targets": [{"type": "text", "label": "ticker", "value": "AAPL"}],
            "credentials": [],
            "output_format": "markdown",
            "execution_mode": "remote",
            "user_notes": "Focus on trend and valuation.",
        },
        headers=_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["selected_skills"][0]["name"] == "clawhub/us-stock-analysis-quick"
    assert body["selected_skills"][0]["quality_tier"] in {"trusted", "strong"}
    assert body["selected_skills"][0]["trust_signals"]
    assert body["workflow_spec"]["nodes"][0]["skill_ref"] == "clawhub/us-stock-analysis-quick"


def test_run_request_uses_ai_rewritten_reply_when_available(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.free_tier_chat_templates.rewrite_planner_response_with_ai",
        lambda **kwargs: (
            PlannerAssistantResponse(
                template_key="free_single_skill_plan",
                headline="AI 改写后的标题",
                reply_text="AI 改写后的免费版说明。",
                usage_steps=["先确认需求。", "再确认执行。"],
                confirmation_prompt="如果可以，请回复确认执行。",
                delivery_note="系统会继续回传结果。",
            ),
            CommunicationPreview(
                template_key="free_single_skill_plan",
                status="pending_confirmation",
                title="AI 改写后的会话标题",
                body="AI 改写后的会话文案。",
                usage_steps=["先确认需求。", "再确认执行。"],
            ),
        ),
    )

    created = client.post(
        "/api/v1/skills/",
        json={
            "name": "clawhub/stock-analyst-ai-copy",
            "display_name": "Stock Analyst",
            "category": "automation",
            "description": "Comprehensive stock analysis with fundamentals and report generation.",
            "summary": "Single-skill stock analysis.",
            "tags": ["stock", "analysis", "report"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
        },
        headers=_headers(),
    )
    assert created.status_code == 201

    response = client.post(
        "/api/v1/run-requests/",
        json={
            "goal": "Analyze AAPL and return a markdown investment brief",
            "targets": [{"type": "text", "label": "ticker", "value": "AAPL"}],
            "credentials": [],
            "output_format": "markdown",
            "execution_mode": "remote",
            "user_notes": "",
        },
        headers=_headers(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["assistant_response"]["headline"] == "AI 改写后的标题"
    assert body["assistant_response"]["reply_text"] == "AI 改写后的免费版说明。"
    assert body["communication_preview"]["body"] == "AI 改写后的会话文案。"


def test_run_request_intake_and_listing(client):
    skill_payloads = [
        {
            "name": "clawhub/web-fetcher-run",
            "display_name": "Web Fetcher",
            "category": "web",
            "description": "fetch report pages from urls",
            "summary": "fetch report pages from urls",
            "tags": ["fetch", "web", "report"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
        },
        {
            "name": "clawhub/report-summarizer-run",
            "display_name": "Report Summarizer",
            "category": "analysis",
            "description": "summarize reports into markdown",
            "summary": "summarize reports into markdown",
            "tags": ["summary", "markdown", "report"],
            "execution_mode": "remote",
            "risk_level": "low",
            "status": "approved",
        },
    ]
    for payload in skill_payloads:
        created = client.post("/api/v1/skills/", json=payload, headers=_headers())
        assert created.status_code == 201

    payload = {
        "goal": "Fetch the monthly incident report from this API and return a markdown summary",
        "targets": [
            {
                "type": "api",
                "label": "Incident endpoint",
                "value": "https://example.com/api/incidents",
            }
        ],
        "credentials": [
            {
                "label": "Partner token",
                "kind": "token",
                "value": "super-secret-token",
                "ephemeral": True,
            }
        ],
        "output_format": "markdown",
        "execution_mode": "remote",
        "user_notes": "Need a customer-facing status summary",
    }
    created = client.post("/api/v1/run-requests/", json=payload, headers=_headers())
    assert created.status_code == 201

    body = created.json()
    assert body["request"]["goal"] == payload["goal"]
    assert body["request"]["credential_descriptors"][0]["preview"] != payload["credentials"][0]["value"]
    assert body["workflow_spec"]["outputs"]["format"] == "markdown"
    assert body["workflow_spec"]["workflow_id"] is not None
    assert len(body["decision_log"]) >= 3
    assert len(body["selected_skills"]) >= 1
    assert body["assistant_response"]["headline"]
    assert body["communication_preview"]["status"] == "pending_confirmation"

    confirmed = client.post(
        f"/api/v1/run-requests/{body['request']['id']}/confirm",
        headers=_headers(),
    )
    assert confirmed.status_code == 200
    confirmed_body = confirmed.json()
    assert confirmed_body["request"]["status"] == "queued"
    assert confirmed_body["communication_preview"]["status"] == "ready_to_send"
    assert confirmed_body["selected_skills"][0]["display_name"]
    assert confirmed_body["selected_skills"][0]["quality_tier"]

    listed = client.get("/api/v1/run-requests/", headers=_headers())
    assert listed.status_code == 200
    assert listed.json()[0]["goal"] == payload["goal"]

    queued_only = client.get("/api/v1/run-requests/?status=queued&limit=10", headers=_headers())
    assert queued_only.status_code == 200
    assert len(queued_only.json()) == 1
    assert queued_only.json()[0]["status"] == "queued"


def test_telemetry_events_support_workflow_and_run_filters(client):
    payloads = [
        {
            "workflow_id": 11,
            "run_id": "run-alpha",
            "node_results": [
                {
                    "node_id": "n1",
                    "status": "success",
                    "output": {"ok": True},
                    "retry_count": 0,
                }
            ],
            "summary": {"success": 1, "failed": 0},
            "client_meta": {"platform": "test"},
        },
        {
            "workflow_id": 12,
            "run_id": "run-beta",
            "node_results": [
                {
                    "node_id": "n2",
                    "status": "failed",
                    "output": {},
                    "error": "boom",
                    "retry_count": 1,
                }
            ],
            "summary": {"success": 0, "failed": 1},
            "client_meta": {"platform": "test"},
        },
    ]

    for payload in payloads:
        response = client.post("/api/v1/telemetry/events", json=payload, headers=_headers())
        assert response.status_code == 200

    by_workflow = client.get("/api/v1/telemetry/events?workflow_id=11", headers=_headers())
    assert by_workflow.status_code == 200
    assert len(by_workflow.json()) == 1
    assert by_workflow.json()[0]["workflow_id"] == 11

    by_run = client.get("/api/v1/telemetry/events?run_id=run-beta", headers=_headers())
    assert by_run.status_code == 200
    assert len(by_run.json()) == 1
    assert by_run.json()[0]["run_id"] == "run-beta"


def test_telemetry_anomaly_export_and_webhook_alert(client, monkeypatch):
    sent = []

    monkeypatch.setattr(
        "app.api.telemetry.send_failure_alert_for_telemetry",
        lambda **kwargs: sent.append(kwargs["event"].run_id) or True,
    )

    payload = {
        "workflow_id": 77,
        "run_id": "run-alert",
        "node_results": [
            {
                "node_id": "n1",
                "status": "failed",
                "output": {},
                "error": "timeout",
                "retry_count": 1,
            }
        ],
        "summary": {"success": 0, "failed": 1},
        "client_meta": {"platform": "client"},
    }
    created = client.post("/api/v1/telemetry/events", json=payload, headers=_headers())
    assert created.status_code == 200
    assert sent == ["run-alert"]

    anomalies = client.get("/api/v1/telemetry/events/anomalies?workflow_id=77", headers=_headers())
    assert anomalies.status_code == 200
    body = anomalies.json()
    assert len(body) == 1
    assert body[0]["run_id"] == "run-alert"
    assert body[0]["failed_node_count"] == 1
    assert body[0]["failed_node_ids"] == ["n1"]

    exported_csv = client.get(
        "/api/v1/telemetry/events/export?workflow_id=77&failed_only=true&format=csv",
        headers=_headers(),
    )
    assert exported_csv.status_code == 200
    assert "text/csv" in exported_csv.headers["content-type"]
    assert "run-alert" in exported_csv.text
    assert "failed_node_count" in exported_csv.text

    exported_jsonl = client.get(
        "/api/v1/telemetry/events/export?workflow_id=77&failed_only=true&format=jsonl",
        headers=_headers(),
    )
    assert exported_jsonl.status_code == 200
    assert "run-alert" in exported_jsonl.text


def test_telemetry_alert_delivery_retries_and_logs(client, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

        @property
        def is_success(self):
            return 200 <= self.status_code < 300

    responses = [
        FakeResponse(500, '{"message":"temporary failure"}'),
        FakeResponse(200, '{"message":"ok"}'),
    ]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args
            _ = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = exc_type
            _ = exc
            _ = tb
            return False

        def post(self, url, json):
            _ = url
            _ = json
            return responses.pop(0)

    monkeypatch.setattr(
        "app.api.telemetry.get_settings",
        lambda: Settings(
            audit_alert_webhook_enabled=True,
            audit_alert_webhook_url="https://hooks.example/flowhub",
            audit_alert_webhook_timeout_seconds=2,
            audit_alert_webhook_max_retries=2,
            audit_alert_webhook_retry_backoff_seconds=0,
        ),
    )
    monkeypatch.setattr("app.services.audit_alerts.httpx.Client", FakeClient)
    monkeypatch.setattr("app.services.audit_alerts.time.sleep", lambda *_args, **_kwargs: None)

    payload = {
        "workflow_id": 88,
        "run_id": "run-alert-retry",
        "node_results": [
            {
                "node_id": "n1",
                "status": "failed",
                "output": {},
                "error": "timeout",
                "retry_count": 2,
            }
        ],
        "summary": {"success": 0, "failed": 1},
        "client_meta": {"platform": "client"},
    }
    created = client.post("/api/v1/telemetry/events", json=payload, headers=_headers())
    assert created.status_code == 200

    listed = client.get("/api/v1/telemetry/alerts?workflow_id=88", headers=_headers())
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["run_id"] == "run-alert-retry"
    assert body[0]["status"] == "delivered"
    assert body[0]["attempt_count"] == 2
    assert body[0]["response_status_code"] == 200
    assert body[0]["destination"] == "https://hooks.example/flowhub"
    assert body[0]["payload"]["run_id"] == "run-alert-retry"

    exported_csv = client.get(
        "/api/v1/telemetry/alerts/export?workflow_id=88&format=csv",
        headers=_headers(),
    )
    assert exported_csv.status_code == 200
    assert "run-alert-retry" in exported_csv.text
    assert "delivered" in exported_csv.text


def test_telemetry_alert_multi_destination_routes_and_replay(client, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

        @property
        def is_success(self):
            return 200 <= self.status_code < 300

    sent: list[tuple[str, dict]] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args
            _ = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = exc_type
            _ = exc
            _ = tb
            return False

        def post(self, url, json):
            sent.append((url, json))
            return FakeResponse(200, '{"message":"ok"}')

    monkeypatch.setattr(
        "app.api.telemetry.get_settings",
        lambda: Settings(
            audit_alert_webhook_enabled=True,
            audit_alert_webhook_destinations_json=(
                '[{"name":"ops","url":"https://hooks.example/ops"},'
                '{"name":"eng","url":"https://hooks.example/eng"}]'
            ),
            audit_alert_webhook_route_rules_json=(
                '[{"name":"default_failed","destinations":["ops"],"when":{"all":true}},'
                '{"name":"client_failures","destinations":["eng"],'
                '"when":{"client_meta_contains":{"platform":"client"}}}]'
            ),
            audit_alert_webhook_timeout_seconds=2,
            audit_alert_webhook_max_retries=1,
            audit_alert_webhook_retry_backoff_seconds=0,
        ),
    )
    monkeypatch.setattr("app.services.audit_alerts.httpx.Client", FakeClient)
    monkeypatch.setattr("app.services.audit_alerts.time.sleep", lambda *_args, **_kwargs: None)

    payload = {
        "workflow_id": 99,
        "run_id": "run-alert-routed",
        "node_results": [
            {
                "node_id": "n1",
                "status": "failed",
                "output": {},
                "error": "timeout",
                "retry_count": 1,
            }
        ],
        "summary": {"success": 0, "failed": 1},
        "client_meta": {"platform": "client"},
    }
    created = client.post("/api/v1/telemetry/events", json=payload, headers=_headers())
    assert created.status_code == 200
    assert [item[0] for item in sent] == ["https://hooks.example/ops", "https://hooks.example/eng"]

    listed = client.get("/api/v1/telemetry/alerts?workflow_id=99", headers=_headers())
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 2
    assert {item["destination"] for item in body} == {"https://hooks.example/ops", "https://hooks.example/eng"}

    ops_delivery = next(item for item in body if item["destination"] == "https://hooks.example/ops")
    eng_delivery = next(item for item in body if item["destination"] == "https://hooks.example/eng")
    assert ops_delivery["payload"]["alert_route"]["destination_name"] == "ops"
    assert ops_delivery["payload"]["alert_route"]["matched_rules"] == ["default_failed"]
    assert eng_delivery["payload"]["alert_route"]["destination_name"] == "eng"
    assert eng_delivery["payload"]["alert_route"]["matched_rules"] == ["client_failures"]

    replayed = client.post(f"/api/v1/telemetry/alerts/{eng_delivery['id']}/replay", headers=_headers())
    assert replayed.status_code == 200
    replay_body = replayed.json()
    assert replay_body["destination"] == "https://hooks.example/eng"
    assert replay_body["payload"]["alert_route"]["replayed_from_delivery_id"] == eng_delivery["id"]

    listed_after = client.get("/api/v1/telemetry/alerts?workflow_id=99", headers=_headers())
    assert listed_after.status_code == 200
    assert len(listed_after.json()) == 3


def test_telemetry_alert_route_rules_support_failed_node_matching(client, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

        @property
        def is_success(self):
            return 200 <= self.status_code < 300

    sent: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args
            _ = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = exc_type
            _ = exc
            _ = tb
            return False

        def post(self, url, json):
            _ = json
            sent.append(url)
            return FakeResponse(200, '{"message":"ok"}')

    monkeypatch.setattr(
        "app.api.telemetry.get_settings",
        lambda: Settings(
            audit_alert_webhook_enabled=True,
            audit_alert_webhook_destinations_json=(
                '[{"name":"ops","url":"https://hooks.example/ops"},'
                '{"name":"db-team","url":"https://hooks.example/db"},'
                '{"name":"tenant-blue","url":"https://hooks.example/tenant-blue"}]'
            ),
            audit_alert_webhook_route_rules_json=(
                '[{"name":"default_failed","destinations":["ops"],"when":{"all":true}},'
                '{"name":"db_errors","destinations":["db-team"],'
                '"when":{"failed_node_error_contains":["database","sqlite"]}},'
                '{"name":"tenant_blue","destinations":["tenant-blue"],'
                '"when":{"client_meta_contains":{"tenant":"blue"}}}]'
            ),
            audit_alert_webhook_timeout_seconds=2,
            audit_alert_webhook_max_retries=1,
            audit_alert_webhook_retry_backoff_seconds=0,
        ),
    )
    monkeypatch.setattr("app.services.audit_alerts.httpx.Client", FakeClient)
    monkeypatch.setattr("app.services.audit_alerts.time.sleep", lambda *_args, **_kwargs: None)

    payload = {
        "workflow_id": 109,
        "run_id": "run-alert-node-match",
        "node_results": [
            {
                "node_id": "db_writer",
                "status": "failed",
                "output": {},
                "error": "SQLite database is locked",
                "retry_count": 1,
            }
        ],
        "summary": {"success": 0, "failed": 1},
        "client_meta": {"platform": "client", "tenant": "blue"},
    }
    created = client.post("/api/v1/telemetry/events", json=payload, headers=_headers())
    assert created.status_code == 200
    assert sent == [
        "https://hooks.example/ops",
        "https://hooks.example/db",
        "https://hooks.example/tenant-blue",
    ]

    listed = client.get("/api/v1/telemetry/alerts?workflow_id=109", headers=_headers())
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 3
    by_destination = {item["destination"]: item for item in body}
    assert by_destination["https://hooks.example/db"]["payload"]["alert_route"]["matched_rules"] == ["db_errors"]
    assert by_destination["https://hooks.example/tenant-blue"]["payload"]["alert_route"]["matched_rules"] == [
        "tenant_blue"
    ]


def test_telemetry_alert_route_rules_support_severity_and_quiet_hours(client, monkeypatch):
    class FakeResponse:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

        @property
        def is_success(self):
            return 200 <= self.status_code < 300

    sent: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            _ = args
            _ = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            _ = exc_type
            _ = exc
            _ = tb
            return False

        def post(self, url, json):
            _ = json
            sent.append(url)
            return FakeResponse(200, '{"message":"ok"}')

    fixed_time = datetime(2026, 3, 13, 23, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.audit_alerts._current_alert_time", lambda _settings: fixed_time)
    monkeypatch.setattr(
        "app.api.telemetry.get_settings",
        lambda: Settings(
            audit_alert_webhook_enabled=True,
            audit_alert_webhook_destinations_json=(
                '[{"name":"ops","url":"https://hooks.example/ops"},'
                '{"name":"pager","url":"https://hooks.example/pager"}]'
            ),
            audit_alert_webhook_route_rules_json=(
                '[{"name":"default_failed","destinations":["ops"],"when":{"all":true}},'
                '{"name":"night_pager","destinations":["pager"],'
                '"when":{"severity_at_least":"high","quiet_hours":{"start_hour":22,"end_hour":8,"allow_critical":true}}}]'
            ),
            audit_alert_webhook_timezone="UTC",
            audit_alert_webhook_timeout_seconds=2,
            audit_alert_webhook_max_retries=1,
            audit_alert_webhook_retry_backoff_seconds=0,
        ),
    )
    monkeypatch.setattr("app.services.audit_alerts.httpx.Client", FakeClient)
    monkeypatch.setattr("app.services.audit_alerts.time.sleep", lambda *_args, **_kwargs: None)

    high_payload = {
        "workflow_id": 120,
        "run_id": "run-alert-high",
        "node_results": [
            {
                "node_id": "n1",
                "status": "failed",
                "output": {},
                "error": "timeout while calling provider",
                "retry_count": 1,
            }
        ],
        "summary": {"success": 0, "failed": 1},
        "client_meta": {"platform": "client"},
    }
    high_created = client.post("/api/v1/telemetry/events", json=high_payload, headers=_headers())
    assert high_created.status_code == 200

    critical_payload = {
        "workflow_id": 121,
        "run_id": "run-alert-critical",
        "node_results": [
            {
                "node_id": "db_writer",
                "status": "failed",
                "output": {},
                "error": "SQLite database is locked",
                "retry_count": 1,
            }
        ],
        "summary": {"success": 0, "failed": 1},
        "client_meta": {"platform": "client"},
    }
    critical_created = client.post("/api/v1/telemetry/events", json=critical_payload, headers=_headers())
    assert critical_created.status_code == 200

    assert sent == [
        "https://hooks.example/ops",
        "https://hooks.example/ops",
        "https://hooks.example/pager",
    ]

    high_deliveries = client.get("/api/v1/telemetry/alerts?workflow_id=120", headers=_headers())
    assert high_deliveries.status_code == 200
    high_body = high_deliveries.json()
    assert len(high_body) == 1
    assert high_body[0]["payload"]["severity"] == "high"

    critical_deliveries = client.get("/api/v1/telemetry/alerts?workflow_id=121", headers=_headers())
    assert critical_deliveries.status_code == 200
    critical_body = critical_deliveries.json()
    assert len(critical_body) == 2
    pager_delivery = next(item for item in critical_body if item["destination"] == "https://hooks.example/pager")
    assert pager_delivery["payload"]["severity"] == "critical"
    assert pager_delivery["payload"]["alert_route"]["matched_rules"] == ["night_pager"]


def test_run_request_export_supports_status_filter(client):
    scenarios = [
        ("planned", "Analyze AAPL and return a markdown investment brief"),
        ("queued", "Fetch this API and return a markdown summary"),
    ]
    for status_value, goal in scenarios:
        created = client.post(
            "/api/v1/run-requests/",
            json={
                "goal": goal,
                "targets": [{"type": "api", "label": "endpoint", "value": "https://example.com/api/data"}],
                "credentials": [],
                "output_format": "markdown",
                "execution_mode": "remote",
                "user_notes": "",
            },
            headers=_headers(),
        )
        assert created.status_code == 201
        if status_value == "queued":
            request_id = created.json()["request"]["id"]
            confirmed = client.post(f"/api/v1/run-requests/{request_id}/confirm", headers=_headers())
            assert confirmed.status_code == 200

    exported = client.get("/api/v1/run-requests/export?status=queued&format=csv", headers=_headers())
    assert exported.status_code == 200
    assert "text/csv" in exported.headers["content-type"]
    assert "queued" in exported.text
