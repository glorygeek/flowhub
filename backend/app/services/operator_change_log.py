from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.operator_change_log import OperatorChangeLog


def append_operator_change_log(
    *,
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    before_state: dict,
    after_state: dict,
    note: str | None = None,
    actor: str | None = None,
) -> OperatorChangeLog:
    row = OperatorChangeLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=(actor or "system").strip() or "system",
        note=(note or "").strip(),
        before_state=before_state,
        after_state=after_state,
    )
    db.add(row)
    db.flush()
    return row


def list_operator_change_logs(
    *,
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str | None = None,
    actor: str | None = None,
    note_q: str | None = None,
    limit: int = 50,
) -> list[OperatorChangeLog]:
    query = build_operator_change_log_query(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        note_q=note_q,
    ).order_by(desc(OperatorChangeLog.created_at), desc(OperatorChangeLog.id)).limit(limit)
    return list(db.scalars(query).all())


def build_operator_change_log_query(
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    action: str | None = None,
    actor: str | None = None,
    note_q: str | None = None,
):
    query = select(OperatorChangeLog)
    if entity_type:
        query = query.where(OperatorChangeLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(OperatorChangeLog.entity_id == entity_id)
    if action:
        query = query.where(OperatorChangeLog.action == action.strip())
    if actor:
        query = query.where(func.lower(OperatorChangeLog.actor) == actor.strip().lower())
    if note_q:
        pattern = f"%{note_q.strip().lower()}%"
        query = query.where(func.lower(OperatorChangeLog.note).like(pattern))
    return query


def list_operator_change_logs_global(
    *,
    db: Session,
    entity_type: str | None = None,
    entity_id: int | None = None,
    action: str | None = None,
    actor: str | None = None,
    note_q: str | None = None,
    limit: int = 100,
) -> list[OperatorChangeLog]:
    query = build_operator_change_log_query(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        note_q=note_q,
    ).order_by(desc(OperatorChangeLog.created_at), desc(OperatorChangeLog.id)).limit(limit)
    return list(db.scalars(query).all())
