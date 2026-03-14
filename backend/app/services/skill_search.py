from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.common import ReviewStatus
from app.models.search_policy_rule import SearchPolicyRule
from app.models.skill import Skill
from app.models.skill_tag_link import SkillTagLink
from app.models.tag_definition import TagDefinition
from app.services.clawhub_sync import ClawHubClient, ClawHubSyncError
from app.services.skill_quality import SkillQualitySummary, summarize_skill_quality
from app.services.skill_security import SkillSecuritySummary, summarize_skill_security

SEARCH_NOISE_TOKENS = {
    "a",
    "an",
    "and",
    "api",
    "for",
    "from",
    "get",
    "how",
    "i",
    "in",
    "is",
    "of",
    "on",
    "or",
    "please",
    "the",
    "to",
    "with",
}
TAG_ALIASES = {
    "股票": {"stock", "stocks", "equity", "equities", "invest", "investment", "finance"},
    "股市": {"stock", "stocks", "equity", "equities", "market", "finance"},
    "美股": {"us", "stock", "stocks", "equity", "finance"},
    "a股": {"china", "stock", "stocks", "equity", "finance"},
    "分析": {"analysis", "analyze", "report"},
    "实时": {"realtime", "real-time", "live", "quote"},
    "新闻": {"news", "headline", "catalyst"},
    "建议": {"recommendation", "entry", "position", "conviction"},
    "投资": {"invest", "investment", "valuation", "portfolio"},
    "market": {"stock", "stocks", "equity", "finance"},
    "stock": {"stock", "stocks", "equity", "finance"},
    "stocks": {"stock", "stocks", "equity", "finance"},
    "ticker": {"stock", "quote", "equity"},
    "news": {"news", "headline", "catalyst"},
    "analysis": {"analysis", "analyze", "report"},
    "invest": {"invest", "investment", "valuation", "portfolio"},
    "investment": {"invest", "investment", "valuation", "portfolio"},
    "aggressive": {"aggressive", "momentum", "signal", "entry"},
}
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
A_SHARE_CODE_PATTERN = re.compile(r"(?<!\d)(?:sh|sz)?[036]\d{5}(?!\d)", re.IGNORECASE)
HK_SHARE_CODE_PATTERN = re.compile(r"(?<!\d)(?:hk)?\d{5}(?!\d)", re.IGNORECASE)
API_FETCH_TERMS = {
    "api",
    "endpoint",
    "fetch",
    "collect",
    "extract",
    "crawl",
    "scrape",
    "json",
    "csv",
    "接口",
    "抓取",
    "提取",
    "导出",
}
CUSTOMER_REPLY_TERMS = {
    "customer",
    "reply",
    "message",
    "notify",
    "notification",
    "markdown",
    "summary",
    "brief",
    "report",
    "客户",
    "回复",
    "简报",
    "通知",
}
COLLECTOR_CAPABILITY_TERMS = {
    "api",
    "endpoint",
    "fetch",
    "collect",
    "extract",
    "crawl",
    "scrape",
    "request",
    "web",
    "rss",
}
PRESENTER_CAPABILITY_TERMS = {
    "summary",
    "summarize",
    "brief",
    "report",
    "markdown",
    "notify",
    "message",
    "reply",
    "response",
    "customer-facing",
}


@dataclass(slots=True)
class SkillSearchHit:
    skill: Skill
    score: float
    retrieval_source: str
    official_score: float | None = None
    quality_score: float = 0.0
    quality_tier: str = "basic"
    trust_signals: list[str] = field(default_factory=list)
    security_score: float = 0.0
    security_tier: str = "caution"
    security_verdict: str = "manual_review_required"
    security_flags: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    matched_tags: list[str] = field(default_factory=list)
    ranking_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SearchDomainIntent:
    wants_equity: bool = False
    wants_china_equity: bool = False
    wants_us_equity: bool = False
    wants_hk_equity: bool = False
    wants_crypto: bool = False
    explicit_a_share: bool = False


@dataclass(slots=True)
class SearchPolicyProfile:
    wants_api_fetch: bool = False
    wants_customer_reply: bool = False


def tokenize_search_text(text: str) -> set[str]:
    raw_tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_\-]+", text.lower())
    tokens: set[str] = set()
    for raw in raw_tokens:
        token = raw.strip("-_")
        if not token or token in SEARCH_NOISE_TOKENS:
            continue
        tokens.add(token)
        if token.endswith("s") and len(token) > 4:
            tokens.add(token[:-1])
        tokens.update(TAG_ALIASES.get(token, set()))
        for phrase, aliases in TAG_ALIASES.items():
            if phrase in token:
                tokens.update(aliases)
    return tokens


def build_skill_haystack(skill: Skill) -> str:
    parts = [
        skill.name or "",
        skill.display_name or "",
        skill.category or "",
        skill.description or "",
        skill.summary or "",
        " ".join(str(tag) for tag in (skill.tags or [])),
        skill.source_slug or "",
        skill.owner_handle or "",
    ]
    return " ".join(parts).lower()


def extract_searchable_tags(skill: Skill) -> set[str]:
    tags: set[str] = set()
    for tag in skill.tags or []:
        if isinstance(tag, str):
            cleaned = tag.strip().lower()
            if cleaned:
                tags.add(cleaned)
                if ":" in cleaned:
                    tags.add(cleaned.split(":", 1)[1])

    payload = skill.source_payload or {}
    for key in ("list", "detail"):
        entry = payload.get(key)
        if not isinstance(entry, dict):
            continue
        skill_payload = entry.get("skill") if key == "detail" else entry
        if not isinstance(skill_payload, dict):
            continue
        raw_tags = skill_payload.get("tags")
        tags.update(_normalize_external_tags(raw_tags))

    metadata = skill.registry_metadata or {}
    tags.update(_normalize_external_tags(metadata.get("official_tags")))
    return {tag for tag in tags if tag}


def load_active_linked_tags(db: Session, skill_ids: list[int]) -> dict[int, set[str]]:
    if not skill_ids:
        return {}

    rows = db.execute(
        select(SkillTagLink.skill_id, TagDefinition.name)
        .join(TagDefinition, TagDefinition.id == SkillTagLink.tag_id)
        .where(SkillTagLink.skill_id.in_(skill_ids), TagDefinition.active.is_(True))
    ).all()
    linked: dict[int, set[str]] = {}
    for skill_id, tag_name in rows:
        linked.setdefault(int(skill_id), set()).add(str(tag_name).lower())
    return linked


def search_skills(
    *,
    db: Session,
    query_text: str,
    limit: int = 10,
    category: str | None = None,
    settings: Settings | None = None,
) -> list[SkillSearchHit]:
    active_settings = settings or get_settings()
    query_tokens = tokenize_search_text(query_text)
    policy_rules = load_active_search_policy_rules(db)
    remote_hits = (
        _fetch_remote_hits(
            query_text=query_text,
            limit=min(max(limit * 3, limit), active_settings.skill_search_default_limit),
            settings=active_settings,
        )
        if active_settings.skill_search_remote_enabled
        else {}
    )

    remote_candidates = _load_remote_candidates(
        db=db,
        remote_hits=remote_hits,
        query_text=query_text,
        query_tokens=query_tokens,
        category=category,
        policy_rules=policy_rules,
    )
    local_candidates = _load_local_candidates(
        db=db,
        query_tokens=query_tokens,
        limit=max(limit * 2, limit),
        category=category,
        include_clawhub=not bool(remote_candidates),
        policy_rules=policy_rules,
    )

    combined: dict[int, SkillSearchHit] = {}
    for hit in remote_candidates + local_candidates:
        current = combined.get(hit.skill.id)
        if current is None or hit.score > current.score:
            combined[hit.skill.id] = hit

    ranked = sorted(
        combined.values(),
        key=lambda item: (
            -item.score,
            item.skill.risk_level.value != "low",
            not item.skill.is_official,
            item.skill.display_name or item.skill.name,
        ),
    )
    return ranked[:limit]


def infer_search_domain_intent(query_text: str, tokens: set[str]) -> SearchDomainIntent:
    lowered_query = query_text.lower()
    explicit_a_share = bool(A_SHARE_CODE_PATTERN.search(lowered_query)) or any(
        marker in lowered_query for marker in ("a股", "a-share", "ashare", "沪深", "上证", "深证", "创业板", "科创板")
    )
    wants_china_equity = bool(tokens & CHINA_MARKET_TERMS) or explicit_a_share
    wants_hk_equity = "港股" in lowered_query or "hong kong" in lowered_query or bool(HK_SHARE_CODE_PATTERN.search(lowered_query))
    wants_us_equity = bool(tokens & US_MARKET_TERMS)
    wants_crypto = bool(tokens & CRYPTO_TERMS)
    wants_equity = bool(tokens & EQUITY_TERMS) or wants_china_equity or wants_us_equity or wants_hk_equity
    return SearchDomainIntent(
        wants_equity=wants_equity,
        wants_china_equity=wants_china_equity,
        wants_us_equity=wants_us_equity,
        wants_hk_equity=wants_hk_equity,
        wants_crypto=wants_crypto,
        explicit_a_share=explicit_a_share,
    )


def infer_search_policy(query_text: str, tokens: set[str]) -> SearchPolicyProfile:
    lowered_query = query_text.lower()
    wants_api_fetch = bool(tokens & API_FETCH_TERMS) or any(
        marker in lowered_query for marker in (" api ", "接口", "endpoint", "json", "csv", "抓取", "提取")
    )
    wants_customer_reply = bool(tokens & CUSTOMER_REPLY_TERMS) or any(
        marker in lowered_query
        for marker in ("customer-facing", "customer", "客户", "回复", "markdown", "summary", "简报", "通知")
    )
    return SearchPolicyProfile(
        wants_api_fetch=wants_api_fetch,
        wants_customer_reply=wants_customer_reply,
    )


def infer_skill_domains(skill: Skill, *, haystack: str, skill_tags: set[str]) -> set[str]:
    combined_tokens = tokenize_search_text(" ".join([haystack, " ".join(sorted(skill_tags))]))
    domains: set[str] = set()

    if combined_tokens & EQUITY_TERMS:
        domains.add("equity")
    if combined_tokens & CHINA_MARKET_TERMS:
        domains.add("china_equity")
    if combined_tokens & US_MARKET_TERMS:
        domains.add("us_equity")
    if "港股" in haystack or "hong kong" in haystack or "hk" in combined_tokens:
        domains.add("hk_equity")
    if combined_tokens & CRYPTO_TERMS:
        domains.add("crypto")
    return domains


def infer_skill_capabilities(*, haystack: str, skill_tags: set[str]) -> set[str]:
    combined_tokens = tokenize_search_text(" ".join([haystack, " ".join(sorted(skill_tags))]))
    capabilities: set[str] = set()
    if combined_tokens & COLLECTOR_CAPABILITY_TERMS:
        capabilities.add("collector")
    if combined_tokens & PRESENTER_CAPABILITY_TERMS or "customer-facing" in haystack:
        capabilities.add("presenter")
    return capabilities


def _fetch_remote_hits(
    *,
    query_text: str,
    limit: int,
    settings: Settings,
) -> dict[str, float]:
    if not query_text.strip():
        return {}

    try:
        with ClawHubClient(settings) as client:
            items = client.search_skills(query_text=query_text, limit=limit)
    except ClawHubSyncError:
        return {}

    hits: dict[str, float] = {}
    for item in items:
        slug = str(item.get("slug") or "").strip().lower()
        if not slug:
            continue
        try:
            score = float(item.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        if score <= 0:
            score = 0.1
        hits[slug] = max(hits.get(slug, 0.0), score)
    return hits


def _load_remote_candidates(
    *,
    db: Session,
    remote_hits: dict[str, float],
    query_text: str,
    query_tokens: set[str],
    category: str | None,
    policy_rules: list[SearchPolicyRule],
) -> list[SkillSearchHit]:
    if not remote_hits:
        return []

    query = select(Skill).where(
        Skill.status == ReviewStatus.approved,
        Skill.source == "clawhub",
        Skill.source_slug.in_(list(remote_hits)),
    )
    if category:
        query = query.where(Skill.category == category)

    skills = db.scalars(query).all()
    linked_tag_map = load_active_linked_tags(db, [skill.id for skill in skills])

    results: list[SkillSearchHit] = []
    for skill in skills:
        score, quality, security, matched_terms, matched_tags, reasons = compute_skill_search_score(
            skill=skill,
            query_text=query_text,
            query_tokens=query_tokens,
            official_score=remote_hits.get((skill.source_slug or "").lower()),
            linked_tags=linked_tag_map.get(skill.id, set()),
            policy_rules=policy_rules,
        )
        results.append(
            SkillSearchHit(
                skill=skill,
                score=score,
                retrieval_source="clawhub_search",
                official_score=remote_hits.get((skill.source_slug or "").lower()),
                quality_score=quality.score,
                quality_tier=quality.tier,
                trust_signals=quality.trust_signals,
                security_score=security.score,
                security_tier=security.tier,
                security_verdict=security.verdict,
                security_flags=security.flags,
                matched_terms=matched_terms,
                matched_tags=matched_tags,
                ranking_reasons=reasons,
            )
        )
    return results


def _load_local_candidates(
    *,
    db: Session,
    query_tokens: set[str],
    limit: int,
    category: str | None,
    include_clawhub: bool,
    policy_rules: list[SearchPolicyRule],
) -> list[SkillSearchHit]:
    query = select(Skill).where(Skill.status == ReviewStatus.approved)
    if category:
        query = query.where(Skill.category == category)
    if not include_clawhub:
        query = query.where(Skill.source != "clawhub")

    skills = db.scalars(query).all()
    linked_tag_map = load_active_linked_tags(db, [skill.id for skill in skills])
    ranked: list[SkillSearchHit] = []
    for skill in skills:
        score, quality, security, matched_terms, matched_tags, reasons = compute_skill_search_score(
            skill=skill,
            query_text=" ".join(sorted(query_tokens)),
            query_tokens=query_tokens,
            official_score=None,
            linked_tags=linked_tag_map.get(skill.id, set()),
            policy_rules=policy_rules,
        )
        if score <= 0:
            continue
        ranked.append(
            SkillSearchHit(
                skill=skill,
                score=score,
                retrieval_source="local_index",
                quality_score=quality.score,
                quality_tier=quality.tier,
                trust_signals=quality.trust_signals,
                security_score=security.score,
                security_tier=security.tier,
                security_verdict=security.verdict,
                security_flags=security.flags,
                matched_terms=matched_terms,
                matched_tags=matched_tags,
                ranking_reasons=reasons,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            item.skill.risk_level.value != "low",
            not item.skill.is_official,
            item.skill.display_name or item.skill.name,
        ),
    )
    return ranked[:limit]


def compute_skill_search_score(
    *,
    skill: Skill,
    query_text: str,
    query_tokens: set[str] | None,
    official_score: float | None,
    linked_tags: set[str] | None = None,
    policy_rules: list[SearchPolicyRule] | None = None,
) -> tuple[float, SkillQualitySummary, SkillSecuritySummary, list[str], list[str], list[str]]:
    tokens = query_tokens or tokenize_search_text(query_text)
    haystack = build_skill_haystack(skill)
    skill_tags = extract_searchable_tags(skill) | (linked_tags or set())
    domain_intent = infer_search_domain_intent(query_text, tokens)
    policy = infer_search_policy(query_text, tokens)
    skill_domains = infer_skill_domains(skill, haystack=haystack, skill_tags=skill_tags)
    skill_capabilities = infer_skill_capabilities(haystack=haystack, skill_tags=skill_tags)
    matched_terms = sorted(token for token in tokens if token and token in haystack)
    matched_tags = sorted(token for token in tokens if token and token in skill_tags)

    text_score = float(len(matched_terms) * 3 + len(matched_tags) * 2)
    quality = summarize_skill_quality(skill)
    security = summarize_skill_security(skill)
    if text_score <= 0 and not official_score:
        return 0.0, quality, security, [], [], []

    score = text_score * 2.2 + quality.score
    reasons: list[str] = []
    if official_score is not None:
        score += official_score * 6.0
        reasons.append(f"ClawHub semantic search score={official_score:.2f}")
    if matched_terms:
        reasons.append("Matched query terms: " + ", ".join(matched_terms[:5]))
    if matched_tags:
        reasons.append("Matched tags: " + ", ".join(matched_tags[:5]))
    if domain_intent.wants_equity and "equity" in skill_domains:
        score += 8.0
        reasons.append("Matched equity-market intent.")
    if domain_intent.wants_china_equity:
        if "china_equity" in skill_domains:
            score += 14.0
            reasons.append("Matched China A-share market intent.")
        elif "us_equity" in skill_domains or "crypto" in skill_domains:
            score -= 8.0
            reasons.append("Downgraded for non-China market focus.")
    if domain_intent.explicit_a_share:
        if "china_equity" in skill_domains:
            score += 18.0
            reasons.append("Matched explicit A-share ticker or market marker.")
        elif "us_equity" in skill_domains or "crypto" in skill_domains:
            score -= 18.0
            reasons.append("Downgraded for explicit A-share request.")
    if domain_intent.wants_us_equity:
        if "us_equity" in skill_domains:
            score += 12.0
            reasons.append("Matched US-equity market intent.")
        elif "china_equity" in skill_domains or "crypto" in skill_domains:
            score -= 6.0
            reasons.append("Downgraded for non-US market focus.")
    if domain_intent.wants_crypto and "crypto" in skill_domains:
        score += 10.0
        reasons.append("Matched crypto-market intent.")
    elif domain_intent.wants_equity and "crypto" in skill_domains:
        score -= 10.0
        reasons.append("Downgraded crypto-focused skill for equity request.")
    configured_delta, configured_reasons = _apply_configured_policy_rules(
        policy=policy,
        domain_intent=domain_intent,
        skill_domains=skill_domains,
        skill_capabilities=skill_capabilities,
        rules=policy_rules or [],
    )
    score += configured_delta
    reasons.extend(configured_reasons)
    if security.tier == "safe":
        score += 4.0
        reasons.append(f"Security tier: {security.tier} (score={security.score:.1f})")
    elif security.tier == "caution":
        score += 1.0
        reasons.append(f"Security tier: {security.tier} (score={security.score:.1f})")
    elif security.tier == "review":
        score -= 8.0
        reasons.append(f"Security tier: {security.tier} (manual review recommended)")
    else:
        score -= 20.0
        reasons.append(f"Security tier: {security.tier} (blocked or quarantine)")
    if security.flags:
        reasons.append("Security flags: " + ", ".join(security.flags[:4]))
    reasons.append(f"Quality tier: {quality.tier} (score={quality.score:.1f})")
    if quality.trust_signals:
        reasons.append("Trust signals: " + ", ".join(quality.trust_signals[:5]))

    return round(score, 4), quality, security, matched_terms, matched_tags, reasons


def _normalize_external_tags(raw_tags: Any) -> set[str]:
    normalized: set[str] = set()
    if isinstance(raw_tags, dict):
        for key in raw_tags:
            if isinstance(key, str):
                cleaned = key.strip().lower()
                if cleaned:
                    normalized.add(cleaned)
    elif isinstance(raw_tags, list):
        for item in raw_tags:
            if isinstance(item, str):
                cleaned = item.strip().lower()
                if cleaned:
                    normalized.add(cleaned)
    elif isinstance(raw_tags, str):
        cleaned = raw_tags.strip().lower()
        if cleaned:
            normalized.add(cleaned)
    return normalized


def load_active_search_policy_rules(db: Session) -> list[SearchPolicyRule]:
    query = (
        select(SearchPolicyRule)
        .where(SearchPolicyRule.active.is_(True))
        .order_by(SearchPolicyRule.priority.asc(), SearchPolicyRule.id.asc())
    )
    return list(db.scalars(query).all())


def _apply_configured_policy_rules(
    *,
    policy: SearchPolicyProfile,
    domain_intent: SearchDomainIntent,
    skill_domains: set[str],
    skill_capabilities: set[str],
    rules: list[SearchPolicyRule],
) -> tuple[float, list[str]]:
    intents = []
    if policy.wants_api_fetch:
        intents.append("api_fetch")
    if policy.wants_customer_reply:
        intents.append("customer_reply")
    if not intents or not rules:
        return 0.0, []

    delta = 0.0
    reasons: list[str] = []
    for intent_key in intents:
        for rule in rules:
            if rule.intent_key != intent_key:
                continue
            if not _search_policy_rule_matches(
                rule=rule,
                domain_intent=domain_intent,
                skill_domains=skill_domains,
                skill_capabilities=skill_capabilities,
            ):
                continue
            delta += float(rule.score_delta)
            if rule.reason:
                reasons.append(rule.reason)
    return delta, reasons


def _search_policy_rule_matches(
    *,
    rule: SearchPolicyRule,
    domain_intent: SearchDomainIntent,
    skill_domains: set[str],
    skill_capabilities: set[str],
) -> bool:
    conditions = rule.conditions or {}
    if not isinstance(conditions, dict):
        return False

    scope = str(conditions.get("query_domain_scope") or "any")
    if not _query_domain_scope_matches(scope, domain_intent):
        return False

    required_domains = _normalize_string_list(conditions.get("skill_domains_any"))
    blocked_domains = _normalize_string_list(conditions.get("skill_domains_none"))
    required_capabilities = _normalize_string_list(conditions.get("skill_capabilities_any"))
    blocked_capabilities = _normalize_string_list(conditions.get("skill_capabilities_none"))

    if required_domains and not (skill_domains & required_domains):
        return False
    if blocked_domains and (skill_domains & blocked_domains):
        return False
    if required_capabilities and not (skill_capabilities & required_capabilities):
        return False
    if blocked_capabilities and (skill_capabilities & blocked_capabilities):
        return False
    return True


def _query_domain_scope_matches(scope: str, domain_intent: SearchDomainIntent) -> bool:
    normalized = scope.strip().lower()
    if normalized in {"", "any"}:
        return True
    if normalized == "non_equity":
        return not domain_intent.wants_equity
    if normalized == "equity":
        return domain_intent.wants_equity
    if normalized == "china_equity":
        return domain_intent.wants_china_equity
    if normalized == "us_equity":
        return domain_intent.wants_us_equity
    if normalized == "hk_equity":
        return domain_intent.wants_hk_equity
    if normalized == "crypto":
        return domain_intent.wants_crypto
    return False


def _normalize_string_list(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    normalized: set[str] = set()
    for item in value:
        if isinstance(item, str):
            cleaned = item.strip().lower()
            if cleaned:
                normalized.add(cleaned)
    return normalized
