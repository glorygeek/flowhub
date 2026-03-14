import csv
import json
from dataclasses import asdict
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.common import RiskLevel, ReviewStatus
from app.models.operator_change_log import OperatorChangeLog
from app.models.search_policy_rule import SearchPolicyRule
from app.models.skill import Skill
from app.models.skill_tag_link import SkillTagLink
from app.models.tag_definition import TagDefinition
from app.schemas.operator_change_log import OperatorChangeLogRead
from app.schemas.search_policy import SearchPolicyRollbackRequest, SearchPolicyRuleRead, SearchPolicyRuleUpdate
from app.schemas.skill_contract import SkillContractCreate, SkillContractRead, SkillContractUpdate
from app.schemas.skill_resolve import SkillResolveRead
from app.schemas.skill_security import SkillSecurityOverrideRead, SkillSecurityOverrideUpdate, SkillSecurityReviewRead
from app.schemas.skill_tags import (
    SkillLinkedTagRead,
    SkillTagAssignmentUpdate,
    SkillTagDefinitionUpdate,
    SkillTagRead,
)
from app.services.clawhub_sync import ClawHubSyncError, sync_clawhub_skills
from app.schemas.skill_search import SkillSearchResultRead
from app.services.skill_search import search_skills
from app.services.skill_tag_index import (
    list_skill_tag_links,
    list_tags,
    replace_operator_tags_for_skill,
    skill_ids_matching_tags,
    sync_skill_tag_links,
)
from app.services.skill_security import (
    extract_security_override,
    replace_security_tags,
    summarize_skill_security,
    write_security_override,
)
from app.services.operator_change_log import (
    append_operator_change_log,
    build_operator_change_log_query,
    list_operator_change_logs_global,
    list_operator_change_logs,
)

router = APIRouter(prefix="/skills", tags=["skills"])

SKILL_TAG_ASSIGNMENT_ENTITY = "skill_operator_tags"
TAG_DEFINITION_ENTITY = "tag_definition"
SEARCH_POLICY_RULE_ENTITY = "search_policy_rule"
SKILL_SECURITY_ENTITY = "skill_security_override"


def normalize_skill_ref(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "/" in text:
        return text.split("/", 1)[1]
    return text


def serialize_skill_contract(skill: Skill) -> SkillContractRead:
    summary = summarize_skill_security(skill)
    payload = SkillContractRead.model_validate(skill)
    return payload.model_copy(
        update={
            "security_score": summary.score,
            "security_tier": summary.tier,
            "security_verdict": summary.verdict,
            "security_flags": summary.flags,
        }
    )


def export_operator_change_logs_response(
    *,
    rows: list[OperatorChangeLog],
    filename: str,
    format: str,
):
    if format == "csv":
        buffer = StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "id",
                "entity_type",
                "entity_id",
                "action",
                "actor",
                "note",
                "before_state",
                "after_state",
                "created_at",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row.id,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "action": row.action,
                    "actor": row.actor,
                    "note": row.note,
                    "before_state": json.dumps(row.before_state, ensure_ascii=False),
                    "after_state": json.dumps(row.after_state, ensure_ascii=False),
                    "created_at": row.created_at.isoformat(),
                }
            )
        return PlainTextResponse(
            buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )

    lines = [
        json.dumps(OperatorChangeLogRead.model_validate(row).model_dump(mode="json"), ensure_ascii=False)
        for row in rows
    ]
    return PlainTextResponse(
        "\n".join(lines),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.jsonl"'},
    )


@router.get("/", response_model=list[SkillContractRead])
def list_skills(
    db: Session = Depends(get_db),
    name: str | None = Query(default=None),
    source: str | None = Query(default=None),
    category: str | None = Query(default=None),
    tags: str | None = Query(default=None, description="Comma-separated tag names"),
    risk_level: RiskLevel | None = Query(default=None),
    status_filter: ReviewStatus | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    query = select(Skill)
    if name:
        query = query.where(Skill.name.ilike(f"%{name}%"))
    if source:
        query = query.where(Skill.source == source)
    if category:
        query = query.where(Skill.category == category)
    if risk_level:
        query = query.where(Skill.risk_level == risk_level)
    if status_filter:
        query = query.where(Skill.status == status_filter)
    if tags:
        skill_ids = skill_ids_matching_tags(db, tags.split(","))
        if not skill_ids:
            return []
        query = query.where(Skill.id.in_(skill_ids))
    query = query.offset(skip).limit(limit)
    return [serialize_skill_contract(skill) for skill in db.scalars(query).all()]


@router.get("/tags", response_model=list[SkillTagRead])
def list_skill_tags(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    rows = list_tags(db=db, q=q, category=category, source=source, limit=limit)
    return [
        SkillTagRead(
            id=tag.id,
            name=tag.name,
            label=tag.label,
            category=tag.category,
            source=tag.source,
            description=tag.description,
            active=tag.active,
            usage_count=usage_count,
            created_at=tag.created_at,
            updated_at=tag.updated_at,
        )
        for tag, usage_count in rows
    ]


@router.put("/tags/{tag_id}", response_model=SkillTagRead)
def update_skill_tag_definition(
    tag_id: int,
    payload: SkillTagDefinitionUpdate,
    db: Session = Depends(get_db),
):
    tag = db.get(TagDefinition, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found.")

    before_state = {
        "name": tag.name,
        "label": tag.label,
        "description": tag.description,
        "active": tag.active,
    }
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in {"change_note", "actor"}:
            continue
        setattr(tag, field, value)
    after_state = {
        "name": tag.name,
        "label": tag.label,
        "description": tag.description,
        "active": tag.active,
    }
    if before_state != after_state:
        append_operator_change_log(
            db=db,
            entity_type=TAG_DEFINITION_ENTITY,
            entity_id=tag.id,
            action="update_tag_definition",
            before_state=before_state,
            after_state=after_state,
            note=payload.change_note,
            actor=payload.actor,
        )
    db.commit()
    db.refresh(tag)

    count = int(
        db.execute(select(func.count(SkillTagLink.id)).where(SkillTagLink.tag_id == tag.id)).scalar_one() or 0
    )
    return SkillTagRead(
        id=tag.id,
        name=tag.name,
        label=tag.label,
        category=tag.category,
        source=tag.source,
        description=tag.description,
        active=tag.active,
        usage_count=count,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
    )


@router.get("/tags/{tag_id}/history", response_model=list[OperatorChangeLogRead])
def list_tag_definition_history(
    tag_id: int,
    db: Session = Depends(get_db),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    tag = db.get(TagDefinition, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found.")
    return list_operator_change_logs(
        db=db,
        entity_type=TAG_DEFINITION_ENTITY,
        entity_id=tag_id,
        actor=actor,
        note_q=note_q,
        limit=limit,
    )


@router.get("/tags/{tag_id}/history/export")
def export_tag_definition_history(
    tag_id: int,
    db: Session = Depends(get_db),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
):
    tag = db.get(TagDefinition, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found.")
    query = (
        build_operator_change_log_query(
            entity_type=TAG_DEFINITION_ENTITY,
            entity_id=tag_id,
            actor=actor,
            note_q=note_q,
        )
        .order_by(OperatorChangeLog.created_at.desc(), OperatorChangeLog.id.desc())
        .limit(limit)
    )
    rows = list(db.scalars(query).all())
    return export_operator_change_logs_response(rows=rows, filename=f"tag-definition-{tag_id}-history", format=format)


@router.get("/search", response_model=list[SkillSearchResultRead])
def search_skill_index(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
    category: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
):
    hits = search_skills(
        db=db,
        query_text=q.strip(),
        limit=limit,
        category=category,
    )
    return [
        SkillSearchResultRead(
            skill=serialize_skill_contract(hit.skill),
            search_score=hit.score,
            retrieval_source=hit.retrieval_source,
            official_score=hit.official_score,
            quality_score=hit.quality_score,
            quality_tier=hit.quality_tier,
            trust_signals=hit.trust_signals,
            security_score=hit.security_score,
            security_tier=hit.security_tier,
            security_verdict=hit.security_verdict,
            security_flags=hit.security_flags,
            matched_terms=hit.matched_terms,
            matched_tags=hit.matched_tags,
            ranking_reasons=hit.ranking_reasons,
        )
        for hit in hits
    ]


@router.get("/resolve", response_model=list[SkillResolveRead])
def resolve_skill_refs(
    refs: str = Query(min_length=1, description="Comma-separated skill refs or source slugs."),
    db: Session = Depends(get_db),
):
    requested_refs: list[str] = []
    seen: set[str] = set()
    for raw_ref in refs.split(","):
        cleaned = raw_ref.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        requested_refs.append(cleaned)

    if not requested_refs:
        return []

    requested_names = {item.lower() for item in requested_refs}
    requested_slugs = {normalize_skill_ref(item) for item in requested_refs if normalize_skill_ref(item)}
    query = select(Skill).where(
        or_(
            func.lower(Skill.name).in_(requested_names),
            func.lower(func.coalesce(Skill.source_slug, "")).in_(requested_slugs),
        )
    )
    rows = list(db.scalars(query).all())
    by_name = {str(skill.name or "").lower(): skill for skill in rows if skill.name}
    by_slug = {
        str(skill.source_slug or "").lower(): skill
        for skill in rows
        if skill.source_slug
    }

    resolved: list[SkillResolveRead] = []
    for requested_ref in requested_refs:
        by_name_key = requested_ref.lower()
        by_slug_key = normalize_skill_ref(requested_ref)
        match: Skill | None = None
        matched_by: str | None = None
        if by_name_key in by_name:
            match = by_name[by_name_key]
            matched_by = "name"
        elif by_slug_key and by_slug_key in by_slug:
            match = by_slug[by_slug_key]
            matched_by = "source_slug"
        resolved.append(
            SkillResolveRead(
                requested_ref=requested_ref,
                matched_by=matched_by,
                skill=serialize_skill_contract(match) if match else None,
            )
        )
    return resolved


@router.get("/search/policies", response_model=list[SearchPolicyRuleRead])
def list_search_policies(db: Session = Depends(get_db)):
    query = select(SearchPolicyRule).order_by(SearchPolicyRule.priority.asc(), SearchPolicyRule.id.asc())
    return [SearchPolicyRuleRead.model_validate(item) for item in db.scalars(query).all()]


@router.put("/search/policies/{rule_id}", response_model=SearchPolicyRuleRead)
def update_search_policy(
    rule_id: int,
    payload: SearchPolicyRuleUpdate,
    db: Session = Depends(get_db),
):
    rule = db.get(SearchPolicyRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Search policy rule not found.")

    before_state = {
        "description": rule.description,
        "reason": rule.reason,
        "conditions": rule.conditions,
        "score_delta": rule.score_delta,
        "priority": rule.priority,
        "active": rule.active,
    }
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in {"change_note", "actor"}:
            continue
        setattr(rule, field, value)
    after_state = {
        "description": rule.description,
        "reason": rule.reason,
        "conditions": rule.conditions,
        "score_delta": rule.score_delta,
        "priority": rule.priority,
        "active": rule.active,
    }
    if before_state != after_state:
        append_operator_change_log(
            db=db,
            entity_type=SEARCH_POLICY_RULE_ENTITY,
            entity_id=rule.id,
            action="update_search_policy_rule",
            before_state=before_state,
            after_state=after_state,
            note=payload.change_note,
            actor=payload.actor,
        )
    db.commit()
    db.refresh(rule)
    return SearchPolicyRuleRead.model_validate(rule)


@router.get("/search/policies/{rule_id}/history", response_model=list[OperatorChangeLogRead])
def list_search_policy_history(
    rule_id: int,
    db: Session = Depends(get_db),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    rule = db.get(SearchPolicyRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Search policy rule not found.")
    return list_operator_change_logs(
        db=db,
        entity_type=SEARCH_POLICY_RULE_ENTITY,
        entity_id=rule_id,
        actor=actor,
        note_q=note_q,
        limit=limit,
    )


@router.get("/search/policies/{rule_id}/history/export")
def export_search_policy_history(
    rule_id: int,
    db: Session = Depends(get_db),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
):
    rule = db.get(SearchPolicyRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Search policy rule not found.")
    query = (
        build_operator_change_log_query(
            entity_type=SEARCH_POLICY_RULE_ENTITY,
            entity_id=rule_id,
            actor=actor,
            note_q=note_q,
        )
        .order_by(OperatorChangeLog.created_at.desc(), OperatorChangeLog.id.desc())
        .limit(limit)
    )
    rows = list(db.scalars(query).all())
    return export_operator_change_logs_response(rows=rows, filename=f"search-policy-{rule_id}-history", format=format)


@router.get("/change-logs", response_model=list[OperatorChangeLogRead])
def list_global_operator_change_logs(
    db: Session = Depends(get_db),
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return list_operator_change_logs_global(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        note_q=note_q,
        limit=limit,
    )


@router.get("/change-logs/export")
def export_global_operator_change_logs(
    db: Session = Depends(get_db),
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
):
    rows = list_operator_change_logs_global(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        note_q=note_q,
        limit=limit,
    )
    return export_operator_change_logs_response(rows=rows, filename="operator-change-logs", format=format)


@router.post("/search/policies/{rule_id}/rollback/{log_id}", response_model=SearchPolicyRuleRead)
def rollback_search_policy(
    rule_id: int,
    log_id: int,
    payload: SearchPolicyRollbackRequest,
    db: Session = Depends(get_db),
):
    rule = db.get(SearchPolicyRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Search policy rule not found.")

    log = db.get(OperatorChangeLog, log_id)
    if log is None or log.entity_type != SEARCH_POLICY_RULE_ENTITY or log.entity_id != rule_id:
        raise HTTPException(status_code=404, detail="Search policy history entry not found.")

    target_state = log.before_state if isinstance(log.before_state, dict) else {}
    before_state = {
        "description": rule.description,
        "reason": rule.reason,
        "conditions": rule.conditions,
        "score_delta": rule.score_delta,
        "priority": rule.priority,
        "active": rule.active,
    }

    for field in ("description", "reason", "conditions", "score_delta", "priority", "active"):
        if field in target_state:
            setattr(rule, field, target_state[field])

    after_state = {
        "description": rule.description,
        "reason": rule.reason,
        "conditions": rule.conditions,
        "score_delta": rule.score_delta,
        "priority": rule.priority,
        "active": rule.active,
    }
    if before_state != after_state:
        append_operator_change_log(
            db=db,
            entity_type=SEARCH_POLICY_RULE_ENTITY,
            entity_id=rule.id,
            action="rollback_search_policy_rule",
            before_state=before_state,
            after_state=after_state,
            note=payload.change_note or f"Rolled back using history #{log_id}.",
            actor=payload.actor,
        )

    db.commit()
    db.refresh(rule)
    return SearchPolicyRuleRead.model_validate(rule)


@router.get("/{skill_id}/tags", response_model=list[SkillLinkedTagRead])
def get_skill_tag_links(skill_id: int, db: Session = Depends(get_db)):
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found.")

    rows = list_skill_tag_links(db, skill_id)
    return [
        SkillLinkedTagRead(
            id=tag.id,
            name=tag.name,
            label=tag.label,
            category=tag.category,
            source=tag.source,
            description=tag.description,
            active=tag.active,
            usage_count=0,
            created_at=tag.created_at,
            updated_at=tag.updated_at,
            link_source=link.source,
            confidence=link.confidence,
        )
        for tag, link in rows
    ]


@router.get("/{skill_id}/tag-history", response_model=list[OperatorChangeLogRead])
def list_skill_tag_history(
    skill_id: int,
    db: Session = Depends(get_db),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return list_operator_change_logs(
        db=db,
        entity_type=SKILL_TAG_ASSIGNMENT_ENTITY,
        entity_id=skill_id,
        actor=actor,
        note_q=note_q,
        limit=limit,
    )


@router.get("/{skill_id}/tag-history/export")
def export_skill_tag_history(
    skill_id: int,
    db: Session = Depends(get_db),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
):
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found.")
    query = (
        build_operator_change_log_query(
            entity_type=SKILL_TAG_ASSIGNMENT_ENTITY,
            entity_id=skill_id,
            actor=actor,
            note_q=note_q,
        )
        .order_by(OperatorChangeLog.created_at.desc(), OperatorChangeLog.id.desc())
        .limit(limit)
    )
    rows = list(db.scalars(query).all())
    return export_operator_change_logs_response(rows=rows, filename=f"skill-{skill_id}-tag-history", format=format)


@router.put("/{skill_id}/tags", response_model=list[SkillLinkedTagRead])
def replace_skill_operator_tags(
    skill_id: int,
    payload: SkillTagAssignmentUpdate,
    db: Session = Depends(get_db),
):
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found.")

    before_rows = list_skill_tag_links(db, skill_id)
    before_tags = [
        tag.name
        for tag, link in before_rows
        if link.source == "operator"
    ]
    replace_operator_tags_for_skill(db, skill, payload.tag_names)
    after_rows = list_skill_tag_links(db, skill_id)
    after_tags = [
        tag.name
        for tag, link in after_rows
        if link.source == "operator"
    ]
    if before_tags != after_tags:
        append_operator_change_log(
            db=db,
            entity_type=SKILL_TAG_ASSIGNMENT_ENTITY,
            entity_id=skill.id,
            action="replace_operator_tags",
            before_state={"tag_names": before_tags},
            after_state={"tag_names": after_tags},
            note=payload.change_note,
            actor=payload.actor,
        )
    db.commit()
    db.refresh(skill)
    rows = list_skill_tag_links(db, skill_id)
    return [
        SkillLinkedTagRead(
            id=tag.id,
            name=tag.name,
            label=tag.label,
            category=tag.category,
            source=tag.source,
            description=tag.description,
            active=tag.active,
            usage_count=0,
            created_at=tag.created_at,
            updated_at=tag.updated_at,
            link_source=link.source,
            confidence=link.confidence,
        )
        for tag, link in rows
    ]


@router.post("/sync/clawhub")
def sync_clawhub(
    full_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    try:
        result = sync_clawhub_skills(db=db, full_refresh=full_refresh)
    except ClawHubSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return asdict(result)


@router.post("/", response_model=SkillContractRead, status_code=status.HTTP_201_CREATED)
def create_skill(payload: SkillContractCreate, db: Session = Depends(get_db)):
    exists = db.scalar(select(Skill).where(Skill.name == payload.name))
    if exists:
        raise HTTPException(status_code=409, detail="Skill name already exists.")
    skill = Skill(**payload.model_dump(mode="json"))
    db.add(skill)
    db.flush()
    sync_skill_tag_links(db, skill)
    db.commit()
    db.refresh(skill)
    return serialize_skill_contract(skill)


@router.get("/{skill_id}/security-review", response_model=SkillSecurityReviewRead)
def get_skill_security_review(skill_id: int, db: Session = Depends(get_db)):
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    summary = summarize_skill_security(skill)
    return SkillSecurityReviewRead(
        security_score=summary.score,
        security_tier=summary.tier,
        security_verdict=summary.verdict,
        security_flags=summary.flags,
        permission_profile=summary.permission_profile,
        moderation_verdict=summary.moderation_verdict,
        operator_override=(
            SkillSecurityOverrideRead.model_validate(summary.operator_override)
            if summary.operator_override
            else None
        ),
    )


@router.get("/{skill_id}/security-history", response_model=list[OperatorChangeLogRead])
def list_skill_security_history(
    skill_id: int,
    db: Session = Depends(get_db),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return list_operator_change_logs(
        db=db,
        entity_type=SKILL_SECURITY_ENTITY,
        entity_id=skill_id,
        actor=actor,
        note_q=note_q,
        limit=limit,
    )


@router.get("/{skill_id}/security-history/export")
def export_skill_security_history(
    skill_id: int,
    db: Session = Depends(get_db),
    actor: str | None = Query(default=None),
    note_q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
):
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found.")
    query = (
        build_operator_change_log_query(
            entity_type=SKILL_SECURITY_ENTITY,
            entity_id=skill_id,
            actor=actor,
            note_q=note_q,
        )
        .order_by(OperatorChangeLog.created_at.desc(), OperatorChangeLog.id.desc())
        .limit(limit)
    )
    rows = list(db.scalars(query).all())
    return export_operator_change_logs_response(rows=rows, filename=f"skill-{skill_id}-security-history", format=format)


@router.put("/{skill_id}/security-review", response_model=SkillSecurityReviewRead)
def update_skill_security_review(
    skill_id: int,
    payload: SkillSecurityOverrideUpdate,
    db: Session = Depends(get_db),
):
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found.")

    current_override = extract_security_override(skill.registry_metadata)
    before_state = {
        "operator_override": current_override,
        "security_profile": summarize_skill_security(skill).as_metadata(),
    }

    skill.registry_metadata = write_security_override(
        skill.registry_metadata,
        decision=payload.decision,
        actor=payload.actor,
        note=payload.change_note,
    )
    summary = summarize_skill_security(skill)
    skill.registry_metadata = {
        **(skill.registry_metadata or {}),
        "security_profile": summary.as_metadata(),
    }
    skill.tags = replace_security_tags(skill.tags, summary)
    sync_skill_tag_links(db, skill)

    after_state = {
        "operator_override": extract_security_override(skill.registry_metadata),
        "security_profile": summary.as_metadata(),
    }
    if before_state != after_state:
        append_operator_change_log(
            db=db,
            entity_type=SKILL_SECURITY_ENTITY,
            entity_id=skill.id,
            action="update_skill_security_override",
            before_state=before_state,
            after_state=after_state,
            note=payload.change_note,
            actor=payload.actor,
        )
    db.commit()
    db.refresh(skill)
    refreshed = summarize_skill_security(skill)
    return SkillSecurityReviewRead(
        security_score=refreshed.score,
        security_tier=refreshed.tier,
        security_verdict=refreshed.verdict,
        security_flags=refreshed.flags,
        permission_profile=refreshed.permission_profile,
        moderation_verdict=refreshed.moderation_verdict,
        operator_override=(
            SkillSecurityOverrideRead.model_validate(refreshed.operator_override)
            if refreshed.operator_override
            else None
        ),
    )


@router.get("/{skill_id}", response_model=SkillContractRead)
def get_skill(skill_id: int, db: Session = Depends(get_db)):
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return serialize_skill_contract(skill)


@router.put("/{skill_id}", response_model=SkillContractRead)
def update_skill(skill_id: int, payload: SkillContractUpdate, db: Session = Depends(get_db)):
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")

    if payload.name and payload.name != skill.name:
        exists = db.scalar(select(Skill).where(Skill.name == payload.name))
        if exists:
            raise HTTPException(status_code=409, detail="Skill name already exists.")

    for field, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(skill, field, value)
    sync_skill_tag_links(db, skill)
    db.commit()
    db.refresh(skill)
    return serialize_skill_contract(skill)


@router.delete("/{skill_id}")
def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    db.delete(skill)
    db.commit()
    return {"deleted": True, "id": skill_id}
