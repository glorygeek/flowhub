from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.common import ExecutionMode, RiskLevel, ReviewStatus
from app.models.skill import Skill
from app.services.skill_quality import build_quality_tags, summarize_skill_quality_inputs
from app.services.skill_security import build_security_tags, summarize_skill_security_inputs
from app.services.skill_tag_index import sync_skill_tag_links

LOGGER = logging.getLogger(__name__)
DEFAULT_SORT = "downloads"
MAX_PAGE_SIZE = 200
SYNC_SOURCE = "clawhub"


class ClawHubSyncError(RuntimeError):
    pass


@dataclass(slots=True)
class SkillSyncResult:
    source: str
    total_seen: int
    created: int
    updated: int
    archived: int
    detail_requests: int
    started_at: datetime
    completed_at: datetime


class ClawHubClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._base_url = settings.clawhub_registry_url.rstrip("/")
        self._page_size = max(1, min(settings.clawhub_sync_page_size, MAX_PAGE_SIZE))
        self._max_retries = max(1, settings.clawhub_sync_max_retries)
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=settings.clawhub_sync_timeout_seconds,
            headers={"Accept": "application/json", "User-Agent": "FlowHubSkillSync/0.1"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ClawHubClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _request_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        delay_seconds = 1.0
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    raise ClawHubSyncError(f"Failed to fetch {path}: {exc}") from exc
                LOGGER.warning("ClawHub request error for %s, retrying in %.1fs", path, delay_seconds)
                time.sleep(delay_seconds)
                delay_seconds *= 2
                continue

            if response.status_code == 429:
                wait_seconds = _retry_delay_seconds(response.headers, delay_seconds)
                LOGGER.warning(
                    "ClawHub rate limited request to %s, waiting %.1fs before retry",
                    path,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
                delay_seconds = min(wait_seconds * 2, 30.0)
                continue

            if response.status_code >= 500:
                if attempt >= self._max_retries:
                    response.raise_for_status()
                LOGGER.warning(
                    "ClawHub server error %s for %s, retrying in %.1fs",
                    response.status_code,
                    path,
                    delay_seconds,
                )
                time.sleep(delay_seconds)
                delay_seconds *= 2
                continue

            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ClawHubSyncError(f"Unexpected payload for {path}: {type(payload)!r}")
            return payload

        raise ClawHubSyncError(f"Exhausted retries for {path}")

    def list_skills(self, *, sort: str = DEFAULT_SORT) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        empty_pages = 0

        while True:
            params: dict[str, Any] = {"sort": sort, "limit": self._page_size}
            if cursor:
                params["cursor"] = cursor
            payload = self._request_json("/api/v1/skills", params=params)
            page_items = payload.get("items") or []
            next_cursor = payload.get("nextCursor")
            if not isinstance(page_items, list):
                raise ClawHubSyncError("ClawHub list response does not contain a list payload")

            if page_items:
                empty_pages = 0
                items.extend(item for item in page_items if isinstance(item, dict))
            else:
                empty_pages += 1
                LOGGER.info("Encountered empty ClawHub page for sort=%s cursor=%s", sort, cursor)

            if not next_cursor or empty_pages >= 3:
                break
            if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
                break

            seen_cursors.add(next_cursor)
            cursor = next_cursor

        return _dedupe_skills(items)

    def get_skill_detail(self, slug: str) -> dict[str, Any]:
        return self._request_json(f"/api/v1/skills/{quote(slug, safe='')}")

    def search_skills(self, query_text: str, *, limit: int = 20) -> list[dict[str, Any]]:
        payload = self._request_json(
            "/api/v1/search",
            params={"q": query_text, "limit": max(1, min(limit, MAX_PAGE_SIZE))},
        )
        results = payload.get("results") or []
        return [item for item in results if isinstance(item, dict)]


def sync_clawhub_skills(
    db: Session,
    *,
    settings: Settings | None = None,
    full_refresh: bool = False,
) -> SkillSyncResult:
    active_settings = settings or get_settings()
    started_at = datetime.now(timezone.utc)

    with ClawHubClient(active_settings) as client:
        list_items = client.list_skills()
        existing_skills = {
            skill.source_slug: skill
            for skill in db.scalars(select(Skill).where(Skill.source == SYNC_SOURCE)).all()
            if skill.source_slug
        }

        created = 0
        updated = 0
        archived = 0
        detail_requests = 0
        seen_slugs: set[str] = set()
        now = datetime.now(timezone.utc)

        for list_item in list_items:
            slug = str(list_item.get("slug") or "").strip().lower()
            if not slug:
                continue

            seen_slugs.add(slug)
            existing = existing_skills.get(slug)
            detail = None
            if _should_refresh_detail(existing=existing, list_item=list_item, full_refresh=full_refresh):
                detail = client.get_skill_detail(slug)
                detail_requests += 1

            detail_payload = detail or _detail_from_existing(existing)
            mapped = _build_skill_payload(
                list_item=list_item,
                detail=detail_payload,
                registry_url=active_settings.clawhub_registry_url,
                synced_at=now,
            )

            if existing is None:
                skill = Skill(**mapped)
                db.add(skill)
                db.flush()
                sync_skill_tag_links(db, skill)
                created += 1
                continue

            for field, value in mapped.items():
                setattr(existing, field, value)
            sync_skill_tag_links(db, existing)
            updated += 1

        for slug, skill in existing_skills.items():
            if slug in seen_slugs or skill.status == ReviewStatus.archived:
                continue
            skill.status = ReviewStatus.archived
            skill.last_synced_at = now
            archived += 1

        db.commit()

    completed_at = datetime.now(timezone.utc)
    return SkillSyncResult(
        source=SYNC_SOURCE,
        total_seen=len(seen_slugs),
        created=created,
        updated=updated,
        archived=archived,
        detail_requests=detail_requests,
        started_at=started_at,
        completed_at=completed_at,
    )


def _should_refresh_detail(
    *,
    existing: Skill | None,
    list_item: dict[str, Any],
    full_refresh: bool,
) -> bool:
    if full_refresh:
        return True
    if existing is None:
        return True

    stored = existing.source_payload or {}
    previous_list = stored.get("list")
    if not isinstance(previous_list, dict):
        return False

    return any(
        previous_list.get(field) != list_item.get(field)
        for field in ("updatedAt", "summary", "displayName", "stats")
    )


def _detail_from_existing(existing: Skill | None) -> dict[str, Any] | None:
    if existing is None:
        return None
    payload = existing.source_payload or {}
    detail = payload.get("detail")
    return detail if isinstance(detail, dict) else None


def _build_skill_payload(
    *,
    list_item: dict[str, Any],
    detail: dict[str, Any] | None,
    registry_url: str,
    synced_at: datetime,
) -> dict[str, Any]:
    detail_skill = detail.get("skill") if isinstance(detail, dict) else None
    latest_version = (
        detail.get("latestVersion")
        if isinstance(detail, dict) and isinstance(detail.get("latestVersion"), dict)
        else list_item.get("latestVersion")
    )
    owner = detail.get("owner") if isinstance(detail, dict) else None
    moderation = detail.get("moderation") if isinstance(detail, dict) else None
    metadata = detail.get("metadata") if isinstance(detail, dict) else list_item.get("metadata")
    official_tags = (
        (detail_skill or {}).get("tags")
        or list_item.get("tags")
        or (detail or {}).get("tags")
        or {}
    )

    slug = str((detail_skill or {}).get("slug") or list_item.get("slug") or "").strip().lower()
    display_name = str((detail_skill or {}).get("displayName") or list_item.get("displayName") or slug)
    summary = str((detail_skill or {}).get("summary") or list_item.get("summary") or "").strip()
    owner_handle = _clean_text((owner or {}).get("handle"))
    description = summary or _clean_text((latest_version or {}).get("changelog")) or display_name
    category = _infer_category(slug=slug, display_name=display_name, summary=summary)
    writes_external_state = _infer_writes_external_state(display_name=display_name, summary=summary)
    risk_level, status = _map_risk_and_status(
        moderation=moderation,
        writes_external_state=writes_external_state,
    )
    version = _clean_text((latest_version or {}).get("version")) or "0.0.0"
    quality_summary = summarize_skill_quality_inputs(
        stats=list_item.get("stats") if isinstance(list_item.get("stats"), dict) else {},
        is_official=owner_handle == "openclaw",
        risk_level=risk_level,
        tags=[],
        source_payload={"detail": detail or {}},
        owner_handle=owner_handle,
    )
    security_summary = summarize_skill_security_inputs(
        name=f"{SYNC_SOURCE}/{slug}",
        display_name=display_name,
        category=category,
        description=description,
        summary=summary,
        tags=[],
        execution_mode=ExecutionMode.local,
        read_only=not writes_external_state,
        writes_external_state=writes_external_state,
        risk_level=risk_level,
        source_payload={"detail": detail or {}},
        owner_handle=owner_handle,
    )
    tags = _build_tags(
        slug=slug,
        category=category,
        owner_handle=owner_handle,
        moderation=moderation,
        latest_version=version,
        metadata=metadata,
        official_tags=official_tags,
        quality_tags=build_quality_tags(quality_summary),
        security_tags=build_security_tags(security_summary),
    )
    normalized_official_tags = _normalize_external_tags(official_tags)
    registry_metadata = metadata if isinstance(metadata, dict) else {}
    if normalized_official_tags:
        registry_metadata = {**registry_metadata, "official_tags": sorted(normalized_official_tags)}
    registry_metadata = {
        **registry_metadata,
        "quality_profile": quality_summary.as_metadata(),
        "security_profile": security_summary.as_metadata(),
    }

    return {
        "name": f"{SYNC_SOURCE}/{slug}",
        "display_name": display_name,
        "category": category,
        "description": description,
        "tags": tags,
        "input_schema": {},
        "output_schema": {},
        "execution_mode": ExecutionMode.local,
        "read_only": not writes_external_state,
        "writes_external_state": writes_external_state,
        "risk_level": risk_level,
        "status": status,
        "is_official": owner_handle == "openclaw",
        "source": SYNC_SOURCE,
        "source_slug": slug,
        "source_url": _build_source_url(registry_url=registry_url, owner_handle=owner_handle, slug=slug),
        "owner_handle": owner_handle,
        "version": version,
        "summary": summary,
        "stats": list_item.get("stats") if isinstance(list_item.get("stats"), dict) else {},
        "registry_metadata": registry_metadata,
        "source_payload": {"list": list_item, "detail": detail or {}},
        "last_synced_at": synced_at,
    }


def _build_tags(
    *,
    slug: str,
    category: str,
    owner_handle: str | None,
    moderation: dict[str, Any] | None,
    latest_version: str,
    metadata: dict[str, Any] | None,
    official_tags: Any,
    quality_tags: list[str],
    security_tags: list[str],
) -> list[str]:
    tags: list[str] = [category, f"source:{SYNC_SOURCE}", f"version:{latest_version}"]
    if owner_handle:
        tags.append(f"owner:{owner_handle}")

    verdict = _clean_text((moderation or {}).get("verdict"))
    if verdict:
        tags.append(f"verdict:{verdict}")

    metadata_os = (metadata or {}).get("os")
    if isinstance(metadata_os, list):
        tags.extend(f"os:{item}" for item in metadata_os if isinstance(item, str) and item)

    tags.extend(sorted(_normalize_external_tags(official_tags)))
    tags.extend(quality_tags)
    tags.extend(security_tags)

    for token in slug.split("-")[:4]:
        if token and token not in tags:
            tags.append(token)

    return sorted(dict.fromkeys(tags))


def _build_source_url(*, registry_url: str, owner_handle: str | None, slug: str) -> str:
    base = registry_url.rstrip("/")
    if owner_handle:
        return f"{base}/{quote(owner_handle, safe='')}/{quote(slug, safe='')}"
    return f"{base}/api/v1/skills/{quote(slug, safe='')}"


def _map_risk_and_status(
    *,
    moderation: dict[str, Any] | None,
    writes_external_state: bool,
) -> tuple[RiskLevel, ReviewStatus]:
    verdict = _clean_text((moderation or {}).get("verdict"))
    if verdict == "malicious":
        return RiskLevel.high, ReviewStatus.rejected
    if verdict == "suspicious":
        return RiskLevel.high, ReviewStatus.pending
    if writes_external_state:
        return RiskLevel.medium, ReviewStatus.approved
    return RiskLevel.low, ReviewStatus.approved


def _infer_category(*, slug: str, display_name: str, summary: str) -> str:
    text = " ".join([slug, display_name, summary]).lower()
    rules = (
        ("browser", "web"),
        ("crawl", "web"),
        ("scrap", "web"),
        ("fetch", "web"),
        ("http", "web"),
        ("github", "developer"),
        ("git ", "developer"),
        ("cli", "developer"),
        ("shell", "developer"),
        ("code", "developer"),
        ("notion", "productivity"),
        ("calendar", "productivity"),
        ("gmail", "productivity"),
        ("drive", "productivity"),
        ("docs", "productivity"),
        ("sheets", "productivity"),
        ("obsidian", "productivity"),
        ("weather", "data"),
        ("search", "data"),
        ("sql", "data"),
        ("csv", "data"),
        ("excel", "data"),
        ("audio", "media"),
        ("video", "media"),
        ("image", "media"),
        ("speech", "media"),
        ("transcrib", "media"),
        ("email", "communication"),
        ("slack", "communication"),
        ("discord", "communication"),
        ("message", "communication"),
    )
    for needle, category in rules:
        if needle in text:
            return category
    return "automation"


def _infer_writes_external_state(*, display_name: str, summary: str) -> bool:
    text = " ".join([display_name, summary]).lower()
    write_keywords = (
        "create",
        "update",
        "delete",
        "publish",
        "post",
        "send",
        "write",
        "edit",
        "manage",
        "control",
        "upload",
        "sync",
    )
    return any(keyword in text for keyword in write_keywords)


def _dedupe_skills(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        slug = str(item.get("slug") or "").strip().lower()
        if slug:
            deduped[slug] = item
    return list(deduped.values())


def _retry_delay_seconds(headers: httpx.Headers, fallback: float) -> float:
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            pass

    rate_limit_reset = headers.get("ratelimit-reset")
    if rate_limit_reset:
        try:
            return max(float(rate_limit_reset), 1.0)
        except ValueError:
            pass

    reset = headers.get("x-ratelimit-reset")
    if reset:
        try:
            return max(float(reset) - time.time(), 1.0)
        except ValueError:
            pass

    return max(fallback, 1.0)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_external_tags(raw_tags: Any) -> set[str]:
    tags: set[str] = set()
    if isinstance(raw_tags, dict):
        items = raw_tags.keys()
    elif isinstance(raw_tags, list):
        items = raw_tags
    elif isinstance(raw_tags, str):
        items = [raw_tags]
    else:
        items = []

    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip().lower()
        if cleaned and cleaned != "latest":
            tags.add(cleaned)
    return tags
