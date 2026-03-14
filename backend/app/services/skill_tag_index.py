from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.skill import Skill
from app.models.skill_tag_link import SkillTagLink
from app.models.tag_definition import TagDefinition
from app.services.skill_quality import summarize_skill_quality

OPERATOR_TAG_SOURCE = "operator"

EQUITY_TERMS = {"stock", "stocks", "equity", "equities", "finance", "market", "shares", "股票", "股市"}
CHINA_MARKET_TERMS = {
    "a股",
    "ashare",
    "a-share",
    "china",
    "cn",
    "中国",
    "沪深",
    "上证",
    "深证",
    "创业板",
    "科创板",
    "shanghai",
    "shenzhen",
    "akshare",
}
US_MARKET_TERMS = {
    "美股",
    "us",
    "usa",
    "nasdaq",
    "nyse",
    "wallstreet",
    "wall-street",
    "american",
}
CRYPTO_TERMS = {"crypto", "cryptocurrency", "bitcoin", "btc", "ethereum", "eth", "token", "defi"}


@dataclass(slots=True)
class DerivedTag:
    name: str
    category: str
    source: str
    description: str = ""
    label: str | None = None
    confidence: str = "high"


def _tag_label(name: str) -> str:
    if ":" in name:
        _, value = name.split(":", 1)
        return value.replace("-", " ").replace("_", " ").strip().title()
    return name.replace("-", " ").replace("_", " ").strip().title()


def _tag_category(name: str) -> str:
    if ":" not in name:
        return "keyword"
    prefix, _ = name.split(":", 1)
    mapping = {
        "source": "source",
        "owner": "owner",
        "verdict": "moderation",
        "version": "version",
        "quality": "quality",
        "signal": "signal",
        "os": "platform",
        "category": "category",
        "domain": "domain",
        "market": "market",
    }
    return mapping.get(prefix, "keyword")


def _build_skill_haystack(skill: Skill) -> str:
    return " ".join(
        [
            skill.name or "",
            skill.display_name or "",
            skill.category or "",
            skill.description or "",
            skill.summary or "",
            " ".join(str(tag) for tag in (skill.tags or [])),
            skill.source_slug or "",
            skill.owner_handle or "",
        ]
    ).lower()


def _normalize_external_tags(raw_tags: object) -> set[str]:
    normalized: set[str] = set()
    if isinstance(raw_tags, dict):
        for key in raw_tags:
            if isinstance(key, str) and key.strip():
                normalized.add(key.strip().lower())
    elif isinstance(raw_tags, list):
        for item in raw_tags:
            if isinstance(item, str) and item.strip():
                normalized.add(item.strip().lower())
    elif isinstance(raw_tags, str) and raw_tags.strip():
        normalized.add(raw_tags.strip().lower())
    return normalized


def _extract_searchable_tags(skill: Skill) -> set[str]:
    tags: set[str] = set()
    for tag in skill.tags or []:
        if isinstance(tag, str) and tag.strip():
            cleaned = tag.strip().lower()
            tags.add(cleaned)
            if ":" in cleaned:
                tags.add(cleaned.split(":", 1)[1])

    metadata = skill.registry_metadata or {}
    tags.update(_normalize_external_tags(metadata.get("official_tags")))
    return {tag for tag in tags if tag}


def _infer_skill_domains(skill: Skill, skill_tags: set[str]) -> set[str]:
    haystack = _build_skill_haystack(skill)
    combined_tokens = {token.lower() for token in skill_tags} | set(haystack.split())
    domains: set[str] = set()
    if combined_tokens & EQUITY_TERMS:
        domains.add("equity")
    if combined_tokens & CHINA_MARKET_TERMS or "a-share" in haystack or "a股" in haystack:
        domains.add("china_equity")
    if combined_tokens & US_MARKET_TERMS:
        domains.add("us_equity")
    if "港股" in haystack or "hong kong" in haystack or " hk " in f" {haystack} ":
        domains.add("hk_equity")
    if combined_tokens & CRYPTO_TERMS:
        domains.add("crypto")
    return domains


def derive_skill_tags(skill: Skill) -> list[DerivedTag]:
    raw_tags = _extract_searchable_tags(skill)
    derived: dict[tuple[str, str], DerivedTag] = {}

    for tag in sorted(raw_tags):
        if not tag:
            continue
        source = "registry" if skill.source == "clawhub" else "manual"
        derived[(tag, source)] = DerivedTag(
            name=tag,
            label=_tag_label(tag),
            category=_tag_category(tag),
            source=source,
            description=f"Indexed tag derived from skill metadata: {tag}",
            confidence="high",
        )

    quality = summarize_skill_quality(skill)
    for tag in [
        f"source:{skill.source}",
        f"category:{skill.category}",
        f"quality:{quality.tier}",
    ]:
        derived[(tag, "rule")] = DerivedTag(
            name=tag,
            label=_tag_label(tag),
            category=_tag_category(tag),
            source="rule",
            description=f"Rule-derived tag for {skill.display_name or skill.name}",
        )

    if skill.is_official:
        derived[("signal:official", "rule")] = DerivedTag(
            name="signal:official",
            label="Official",
            category="signal",
            source="rule",
            description="Skill published by an official source.",
        )

    domains = _infer_skill_domains(skill, raw_tags)
    for domain in sorted(domains):
        tag_name = f"domain:{domain}"
        derived[(tag_name, "rule")] = DerivedTag(
            name=tag_name,
            label=_tag_label(tag_name),
            category="domain",
            source="rule",
            description=f"Domain routing tag for {domain}",
        )

    return sorted(derived.values(), key=lambda item: (item.category, item.name, item.source))


def sync_skill_tag_links(db: Session, skill: Skill) -> None:
    if skill.id is None:
        db.flush()

    derived_tags = derive_skill_tags(skill)
    db.query(SkillTagLink).filter(
        SkillTagLink.skill_id == skill.id,
        SkillTagLink.source != OPERATOR_TAG_SOURCE,
    ).delete(synchronize_session=False)

    for item in derived_tags:
        tag = db.scalar(select(TagDefinition).where(TagDefinition.name == item.name))
        if tag is None:
            tag = TagDefinition(
                name=item.name,
                label=item.label or _tag_label(item.name),
                category=item.category,
                source=item.source,
                description=item.description,
                active=True,
            )
            db.add(tag)
            db.flush()
        else:
            tag.label = item.label or tag.label or _tag_label(item.name)
            tag.category = item.category
            tag.source = item.source
            tag.description = item.description

        db.add(
            SkillTagLink(
                skill_id=skill.id,
                tag_id=tag.id,
                source=item.source,
                confidence=item.confidence,
            )
        )


def list_tags(
    *,
    db: Session,
    q: str | None = None,
    category: str | None = None,
    source: str | None = None,
    limit: int = 100,
) -> list[tuple[TagDefinition, int]]:
    query = (
        select(TagDefinition, func.count(SkillTagLink.id).label("usage_count"))
        .select_from(TagDefinition)
        .join(SkillTagLink, SkillTagLink.tag_id == TagDefinition.id, isouter=True)
        .group_by(TagDefinition.id)
        .order_by(TagDefinition.category, TagDefinition.name)
    )
    if q:
        pattern = f"%{q.lower()}%"
        query = query.where(
            func.lower(TagDefinition.name).like(pattern) | func.lower(TagDefinition.label).like(pattern)
        )
    if category:
        query = query.where(TagDefinition.category == category)
    if source:
        query = query.where(TagDefinition.source == source)
    query = query.limit(limit)

    return [(row[0], int(row[1] or 0)) for row in db.execute(query).all()]


def ensure_tag_definition(
    *,
    db: Session,
    name: str,
    source: str = OPERATOR_TAG_SOURCE,
    label: str | None = None,
    category: str | None = None,
    description: str = "",
) -> TagDefinition:
    normalized_name = name.strip().lower()
    tag = db.scalar(select(TagDefinition).where(TagDefinition.name == normalized_name))
    if tag is None:
        tag = TagDefinition(
            name=normalized_name,
            label=label or _tag_label(normalized_name),
            category=category or _tag_category(normalized_name),
            source=source,
            description=description or f"Operator-managed tag: {normalized_name}",
            active=True,
        )
        db.add(tag)
        db.flush()
        return tag

    if label:
        tag.label = label
    if category:
        tag.category = category
    if description:
        tag.description = description
    return tag


def replace_operator_tags_for_skill(db: Session, skill: Skill, tag_names: list[str]) -> list[SkillTagLink]:
    if skill.id is None:
        db.flush()

    normalized = []
    seen: set[str] = set()
    for item in tag_names:
        cleaned = item.strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    db.query(SkillTagLink).filter(
        SkillTagLink.skill_id == skill.id,
        SkillTagLink.source == OPERATOR_TAG_SOURCE,
    ).delete(synchronize_session=False)

    links: list[SkillTagLink] = []
    for tag_name in normalized:
        tag = ensure_tag_definition(db=db, name=tag_name)
        link = SkillTagLink(
            skill_id=skill.id,
            tag_id=tag.id,
            source=OPERATOR_TAG_SOURCE,
            confidence="high",
        )
        db.add(link)
        links.append(link)
    db.flush()
    return links


def list_skill_tag_links(db: Session, skill_id: int) -> list[tuple[TagDefinition, SkillTagLink]]:
    rows = db.execute(
        select(TagDefinition, SkillTagLink)
        .join(SkillTagLink, SkillTagLink.tag_id == TagDefinition.id)
        .where(SkillTagLink.skill_id == skill_id)
        .order_by(TagDefinition.category, TagDefinition.name, SkillTagLink.source)
    ).all()
    return [(row[0], row[1]) for row in rows]


def skill_ids_matching_tags(db: Session, tag_names: list[str]) -> set[int]:
    normalized = [item.strip().lower() for item in tag_names if item.strip()]
    if not normalized:
        return set()

    rows = db.execute(
        select(SkillTagLink.skill_id, TagDefinition.name)
        .join(TagDefinition, TagDefinition.id == SkillTagLink.tag_id)
        .where(TagDefinition.name.in_(normalized), TagDefinition.active.is_(True))
    ).all()

    matched: dict[int, set[str]] = {}
    for skill_id, tag_name in rows:
        matched.setdefault(skill_id, set()).add(str(tag_name).lower())

    expected = set(normalized)
    return {skill_id for skill_id, tags in matched.items() if expected.issubset(tags)}
