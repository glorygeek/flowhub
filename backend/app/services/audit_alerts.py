from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.audit_alert_delivery import AuditAlertDelivery
from app.models.telemetry import TelemetryEvent

LOGGER = logging.getLogger(__name__)
SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class AlertDestination:
    name: str
    url: str
    matched_rules: list[str] = field(default_factory=list)


def telemetry_event_has_failures(event: TelemetryEvent) -> bool:
    if int(event.summary.get("failed") or 0) > 0:
        return True
    return any(str(item.get("status") or "") == "failed" for item in (event.node_results or []))


def classify_telemetry_alert_severity(failed_nodes: list[dict[str, Any]]) -> str:
    if not failed_nodes:
        return "low"

    errors = " ".join(str(item.get("error") or "").lower() for item in failed_nodes)
    failed_count = len(failed_nodes)

    if failed_count >= 3 or any(term in errors for term in ("database", "sqlite", "auth", "credential", "security")):
        return "critical"
    if failed_count >= 2 or any(term in errors for term in ("timeout", "rate limit", "connection", "unavailable")):
        return "high"
    if failed_count >= 1:
        return "medium"
    return "low"


def build_telemetry_alert_payload(event: TelemetryEvent) -> dict[str, Any]:
    failed_nodes = [
        {
            "node_id": item.get("node_id"),
            "status": item.get("status"),
            "error": item.get("error"),
            "retry_count": item.get("retry_count", 0),
        }
        for item in (event.node_results or [])
        if str(item.get("status") or "") == "failed"
    ]
    severity = classify_telemetry_alert_severity(failed_nodes)
    return {
        "event": "flowhub.telemetry.failed",
        "workflow_id": event.workflow_id,
        "run_id": event.run_id,
        "severity": severity,
        "failed_node_count": len(failed_nodes),
        "failed_nodes": failed_nodes,
        "summary": event.summary,
        "client_meta": event.client_meta,
        "created_at": event.created_at.isoformat(),
    }


def _truncate_preview(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


def _current_alert_time(settings: Settings) -> datetime:
    try:
        zone = ZoneInfo(settings.audit_alert_webhook_timezone)
    except Exception:
        zone = timezone.utc
    return datetime.now(zone)


def _is_quiet_hours_match(quiet_hours: dict[str, Any], settings: Settings, severity: str) -> bool:
    try:
        start_hour = int(quiet_hours.get("start_hour"))
        end_hour = int(quiet_hours.get("end_hour"))
    except (TypeError, ValueError):
        return False
    allow_critical = bool(quiet_hours.get("allow_critical", True))
    if allow_critical and severity == "critical":
        return False

    current_hour = _current_alert_time(settings).hour
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= current_hour < end_hour
    return current_hour >= start_hour or current_hour < end_hour


def _parse_alert_destinations(settings: Settings) -> list[AlertDestination]:
    raw = (settings.audit_alert_webhook_destinations_json or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            LOGGER.warning("Invalid AUDIT_ALERT_WEBHOOK_DESTINATIONS_JSON, ignoring custom destinations.")
            parsed = []
        if isinstance(parsed, list):
            items: list[AlertDestination] = []
            for entry in parsed:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or "").strip()
                url = str(entry.get("url") or "").strip()
                if not name or not url:
                    continue
                items.append(AlertDestination(name=name, url=url))
            if items:
                return items

    if settings.audit_alert_webhook_url:
        return [AlertDestination(name="default", url=settings.audit_alert_webhook_url)]
    return []


def _matches_route_rule(rule: dict[str, Any], payload: dict[str, Any], event: TelemetryEvent, settings: Settings) -> bool:
    when = rule.get("when")
    if not isinstance(when, dict) or not when:
        return True
    if when.get("all") is True:
        return True

    failed_nodes = payload.get("failed_nodes") if isinstance(payload.get("failed_nodes"), list) else []
    severity = str(payload.get("severity") or "low").lower()

    workflow_ids = when.get("workflow_ids")
    if isinstance(workflow_ids, list) and workflow_ids:
        try:
            normalized_ids = {int(item) for item in workflow_ids}
        except (TypeError, ValueError):
            normalized_ids = set()
        if event.workflow_id not in normalized_ids:
            return False

    run_id_prefixes = when.get("run_id_prefixes")
    if isinstance(run_id_prefixes, list) and run_id_prefixes:
        prefixes = [str(item).strip() for item in run_id_prefixes if str(item).strip()]
        if prefixes and not any(event.run_id.startswith(prefix) for prefix in prefixes):
            return False

    failed_node_count_gte = when.get("failed_node_count_gte")
    if failed_node_count_gte is not None:
        try:
            if int(payload.get("failed_node_count") or 0) < int(failed_node_count_gte):
                return False
        except (TypeError, ValueError):
            return False

    severity_any = when.get("severity_any")
    if isinstance(severity_any, list) and severity_any:
        normalized = {str(item).strip().lower() for item in severity_any if str(item).strip()}
        if normalized and severity not in normalized:
            return False

    severity_at_least = when.get("severity_at_least")
    if severity_at_least:
        threshold = str(severity_at_least).strip().lower()
        if SEVERITY_ORDER.get(severity, 0) < SEVERITY_ORDER.get(threshold, 0):
            return False

    client_meta_contains = when.get("client_meta_contains")
    if isinstance(client_meta_contains, dict) and client_meta_contains:
        client_meta = event.client_meta or {}
        for key, expected in client_meta_contains.items():
            if str(client_meta.get(str(key))) != str(expected):
                return False

    failed_node_ids_any = when.get("failed_node_ids_any")
    if isinstance(failed_node_ids_any, list) and failed_node_ids_any:
        normalized_ids = {str(item).strip() for item in failed_node_ids_any if str(item).strip()}
        event_failed_ids = {str(item.get("node_id") or "").strip() for item in failed_nodes if item.get("node_id")}
        if normalized_ids and not (normalized_ids & event_failed_ids):
            return False

    failed_node_error_contains = when.get("failed_node_error_contains")
    if failed_node_error_contains:
        expected_terms = (
            [str(item).strip().lower() for item in failed_node_error_contains if str(item).strip()]
            if isinstance(failed_node_error_contains, list)
            else [str(failed_node_error_contains).strip().lower()]
        )
        errors = [str(item.get("error") or "").lower() for item in failed_nodes if item.get("error")]
        if expected_terms and not any(term in error for term in expected_terms for error in errors):
            return False

    quiet_hours = when.get("quiet_hours")
    if isinstance(quiet_hours, dict) and quiet_hours:
        if _is_quiet_hours_match(quiet_hours, settings, severity):
            return False

    return True


def _resolve_alert_destinations(
    *,
    settings: Settings,
    event: TelemetryEvent,
    payload: dict[str, Any],
) -> list[AlertDestination]:
    destinations = _parse_alert_destinations(settings)
    if not destinations:
        return []

    by_name = {item.name: AlertDestination(name=item.name, url=item.url) for item in destinations}
    raw_rules = (settings.audit_alert_webhook_route_rules_json or "").strip()
    if not raw_rules:
        return list(by_name.values())

    try:
        parsed_rules = json.loads(raw_rules)
    except json.JSONDecodeError:
        LOGGER.warning("Invalid AUDIT_ALERT_WEBHOOK_ROUTE_RULES_JSON, defaulting to all destinations.")
        return list(by_name.values())

    if not isinstance(parsed_rules, list):
        return list(by_name.values())

    matched: dict[str, AlertDestination] = {}
    for index, rule in enumerate(parsed_rules, start=1):
        if not isinstance(rule, dict):
            continue
        if rule.get("active") is False:
            continue
        if not _matches_route_rule(rule, payload, event, settings):
            continue
        rule_name = str(rule.get("name") or f"rule_{index}").strip() or f"rule_{index}"
        destination_names = rule.get("destinations")
        if not isinstance(destination_names, list):
            continue
        for destination_name in destination_names:
            normalized = str(destination_name).strip()
            if not normalized or normalized not in by_name:
                continue
            target = matched.setdefault(
                normalized,
                AlertDestination(
                    name=by_name[normalized].name,
                    url=by_name[normalized].url,
                    matched_rules=[],
                ),
            )
            if rule_name not in target.matched_rules:
                target.matched_rules.append(rule_name)

    return list(matched.values())


def _deliver_failure_alert(
    *,
    db: Session,
    event: TelemetryEvent,
    settings: Settings,
    destination: AlertDestination,
    payload: dict[str, Any],
) -> AuditAlertDelivery:
    max_attempts = max(1, int(settings.audit_alert_webhook_max_retries) + 1)
    attempt_count = 0
    delivered = False
    response_status_code: int | None = None
    response_body_preview = ""
    error_message = ""
    delivered_at = None

    with httpx.Client(timeout=settings.audit_alert_webhook_timeout_seconds) as client:
        for attempt in range(1, max_attempts + 1):
            attempt_count = attempt
            try:
                response = client.post(destination.url, json=payload)
                response_status_code = response.status_code
                response_body_preview = _truncate_preview(
                    response.text or "",
                    settings.audit_alert_webhook_response_preview_chars,
                )
                if response.is_success:
                    delivered = True
                    delivered_at = datetime.now(timezone.utc)
                    error_message = ""
                    break
                error_message = f"HTTP {response.status_code}: {response_body_preview or 'No response body'}"
            except httpx.HTTPError as exc:
                error_message = str(exc)

            if attempt < max_attempts:
                time.sleep(max(settings.audit_alert_webhook_retry_backoff_seconds * attempt, 0.0))

    row = AuditAlertDelivery(
        telemetry_event_id=event.id,
        workflow_id=event.workflow_id,
        run_id=event.run_id,
        destination=destination.url,
        status="delivered" if delivered else "failed",
        attempt_count=attempt_count,
        response_status_code=response_status_code,
        response_body_preview=response_body_preview,
        error_message=error_message,
        payload=payload,
        delivered_at=delivered_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if not delivered and error_message:
        LOGGER.warning(
            "Audit alert webhook failed for %s after %s attempts: %s",
            destination.url,
            attempt_count,
            error_message,
        )
    return row


def send_failure_alert_for_telemetry(
    *,
    db: Session,
    event: TelemetryEvent,
    settings: Settings,
) -> list[AuditAlertDelivery]:
    if not settings.audit_alert_webhook_enabled:
        return []
    if not telemetry_event_has_failures(event):
        return []

    payload = build_telemetry_alert_payload(event)
    destinations = _resolve_alert_destinations(settings=settings, event=event, payload=payload)
    if not destinations:
        return []

    rows: list[AuditAlertDelivery] = []
    for destination in destinations:
        delivery_payload = {
            **payload,
            "alert_route": {
                "destination_name": destination.name,
                "matched_rules": destination.matched_rules,
            },
        }
        rows.append(
            _deliver_failure_alert(
                db=db,
                event=event,
                settings=settings,
                destination=destination,
                payload=delivery_payload,
            )
        )
    return rows


def replay_failure_alert_delivery(
    *,
    db: Session,
    event: TelemetryEvent,
    delivery: AuditAlertDelivery,
    settings: Settings,
) -> AuditAlertDelivery | None:
    if not settings.audit_alert_webhook_enabled:
        return None
    if not telemetry_event_has_failures(event):
        return None

    route_meta = delivery.payload.get("alert_route") if isinstance(delivery.payload, dict) else {}
    destination = AlertDestination(
        name=str(route_meta.get("destination_name") or "replay").strip() or "replay",
        url=delivery.destination,
        matched_rules=[
            str(item).strip()
            for item in (route_meta.get("matched_rules") if isinstance(route_meta, dict) else [])
            if str(item).strip()
        ],
    )
    payload = {
        **build_telemetry_alert_payload(event),
        "alert_route": {
            "destination_name": destination.name,
            "matched_rules": destination.matched_rules,
            "replayed_from_delivery_id": delivery.id,
        },
    }
    return _deliver_failure_alert(
        db=db,
        event=event,
        settings=settings,
        destination=destination,
        payload=payload,
    )
