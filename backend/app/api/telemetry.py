import csv
import json
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.audit_alert_delivery import AuditAlertDelivery
from app.models.telemetry import TelemetryEvent
from app.schemas.telemetry import (
    TelemetryAck,
    TelemetryAlertDeliveryRead,
    TelemetryAnomalyRead,
    TelemetryEventCreate,
    TelemetryEventRead,
)
from app.services.audit_alerts import (
    replay_failure_alert_delivery,
    send_failure_alert_for_telemetry,
    telemetry_event_has_failures,
)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/events", response_model=TelemetryAck)
def ingest_event(payload: TelemetryEventCreate, db: Session = Depends(get_db)):
    event = TelemetryEvent(**payload.model_dump(mode="json"))
    db.add(event)
    db.commit()
    db.refresh(event)
    send_failure_alert_for_telemetry(db=db, event=event, settings=get_settings())
    return TelemetryAck(accepted=True, ingested_at=event.created_at)


@router.get("/events", response_model=list[TelemetryEventRead])
def list_events(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    workflow_id: int | None = Query(default=None),
    run_id: str | None = Query(default=None),
):
    query = select(TelemetryEvent)
    if workflow_id is not None:
        query = query.where(TelemetryEvent.workflow_id == workflow_id)
    if run_id:
        query = query.where(TelemetryEvent.run_id == run_id)
    query = query.order_by(desc(TelemetryEvent.created_at)).limit(limit)
    return list(db.scalars(query).all())


@router.get("/events/anomalies", response_model=list[TelemetryAnomalyRead])
def list_anomalies(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    workflow_id: int | None = Query(default=None),
    run_id: str | None = Query(default=None),
):
    query = select(TelemetryEvent)
    if workflow_id is not None:
        query = query.where(TelemetryEvent.workflow_id == workflow_id)
    if run_id:
        query = query.where(TelemetryEvent.run_id == run_id)
    query = query.order_by(desc(TelemetryEvent.created_at)).limit(limit)

    anomalies: list[TelemetryAnomalyRead] = []
    for event in db.scalars(query).all():
        if not telemetry_event_has_failures(event):
            continue
        failed_node_ids = [
            str(item.get("node_id"))
            for item in (event.node_results or [])
            if str(item.get("status") or "") == "failed"
        ]
        anomalies.append(
            TelemetryAnomalyRead(
                event_id=event.id,
                workflow_id=event.workflow_id,
                run_id=event.run_id,
                failed_node_count=len(failed_node_ids),
                failed_node_ids=failed_node_ids,
                summary=event.summary,
                client_meta=event.client_meta,
                created_at=event.created_at,
            )
        )
    return anomalies


@router.get("/events/export")
def export_events(
    db: Session = Depends(get_db),
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
    limit: int = Query(default=200, ge=1, le=2000),
    workflow_id: int | None = Query(default=None),
    run_id: str | None = Query(default=None),
    failed_only: bool = Query(default=False),
):
    query = select(TelemetryEvent)
    if workflow_id is not None:
        query = query.where(TelemetryEvent.workflow_id == workflow_id)
    if run_id:
        query = query.where(TelemetryEvent.run_id == run_id)
    query = query.order_by(desc(TelemetryEvent.created_at)).limit(limit)
    events = list(db.scalars(query).all())
    if failed_only:
        events = [event for event in events if telemetry_event_has_failures(event)]

    if format == "csv":
        buffer = StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "event_id",
                "workflow_id",
                "run_id",
                "failed",
                "failed_node_count",
                "created_at",
                "summary",
                "client_meta",
            ],
        )
        writer.writeheader()
        for event in events:
            failed_node_count = sum(
                1 for item in (event.node_results or []) if str(item.get("status") or "") == "failed"
            )
            writer.writerow(
                {
                    "event_id": event.id,
                    "workflow_id": event.workflow_id,
                    "run_id": event.run_id,
                    "failed": int(telemetry_event_has_failures(event)),
                    "failed_node_count": failed_node_count,
                    "created_at": event.created_at.isoformat(),
                    "summary": json.dumps(event.summary, ensure_ascii=False),
                    "client_meta": json.dumps(event.client_meta, ensure_ascii=False),
                }
            )
        return PlainTextResponse(
            buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="telemetry-events.csv"'},
        )

    lines = []
    for event in events:
        lines.append(
            json.dumps(
                {
                    "event_id": event.id,
                    "workflow_id": event.workflow_id,
                    "run_id": event.run_id,
                    "node_results": event.node_results,
                    "summary": event.summary,
                    "client_meta": event.client_meta,
                    "created_at": event.created_at.isoformat(),
                },
                ensure_ascii=False,
            )
        )
    return PlainTextResponse(
        "\n".join(lines),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="telemetry-events.jsonl"'},
    )


@router.get("/alerts", response_model=list[TelemetryAlertDeliveryRead])
def list_alert_deliveries(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    workflow_id: int | None = Query(default=None),
    run_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    query = select(AuditAlertDelivery)
    if workflow_id is not None:
        query = query.where(AuditAlertDelivery.workflow_id == workflow_id)
    if run_id:
        query = query.where(AuditAlertDelivery.run_id == run_id)
    if status:
        query = query.where(AuditAlertDelivery.status == status)
    query = query.order_by(desc(AuditAlertDelivery.created_at), desc(AuditAlertDelivery.id)).limit(limit)
    return list(db.scalars(query).all())


@router.get("/alerts/export")
def export_alert_deliveries(
    db: Session = Depends(get_db),
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
    limit: int = Query(default=200, ge=1, le=2000),
    workflow_id: int | None = Query(default=None),
    run_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    query = select(AuditAlertDelivery)
    if workflow_id is not None:
        query = query.where(AuditAlertDelivery.workflow_id == workflow_id)
    if run_id:
        query = query.where(AuditAlertDelivery.run_id == run_id)
    if status:
        query = query.where(AuditAlertDelivery.status == status)
    query = query.order_by(desc(AuditAlertDelivery.created_at), desc(AuditAlertDelivery.id)).limit(limit)
    items = list(db.scalars(query).all())

    if format == "csv":
        buffer = StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "id",
                "telemetry_event_id",
                "workflow_id",
                "run_id",
                "status",
                "attempt_count",
                "response_status_code",
                "destination",
                "error_message",
                "created_at",
                "delivered_at",
            ],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "id": item.id,
                    "telemetry_event_id": item.telemetry_event_id,
                    "workflow_id": item.workflow_id,
                    "run_id": item.run_id,
                    "status": item.status,
                    "attempt_count": item.attempt_count,
                    "response_status_code": item.response_status_code,
                    "destination": item.destination,
                    "error_message": item.error_message,
                    "created_at": item.created_at.isoformat(),
                    "delivered_at": item.delivered_at.isoformat() if item.delivered_at else "",
                }
            )
        return PlainTextResponse(
            buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="audit-alert-deliveries.csv"'},
        )

    lines = [
        json.dumps(TelemetryAlertDeliveryRead.model_validate(item).model_dump(mode="json"), ensure_ascii=False)
        for item in items
    ]
    return PlainTextResponse(
        "\n".join(lines),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit-alert-deliveries.jsonl"'},
    )


@router.post("/alerts/{delivery_id}/replay", response_model=TelemetryAlertDeliveryRead)
def replay_alert_delivery(delivery_id: int, db: Session = Depends(get_db)):
    delivery = db.get(AuditAlertDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Alert delivery not found.")

    event = db.get(TelemetryEvent, delivery.telemetry_event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Telemetry event not found for alert delivery.")

    replayed = replay_failure_alert_delivery(
        db=db,
        event=event,
        delivery=delivery,
        settings=get_settings(),
    )
    if replayed is None:
        raise HTTPException(status_code=409, detail="Audit alert webhook is not enabled.")
    return replayed
