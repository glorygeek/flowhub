from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.models.common import RiskLevel
from app.models.skill import Skill

TRUSTED_MODERATION_VERDICTS = {"approved", "clean", "pass", "safe", "trusted", "verified"}
SUSPICIOUS_MODERATION_VERDICTS = {"blocked", "rejected", "suspicious", "unsafe"}


@dataclass(slots=True)
class SkillQualitySummary:
    score: float
    tier: str
    trust_signals: list[str]
    community_validated_proxy: bool
    official_validated: bool
    moderation_verdict: str | None
    stats_snapshot: dict[str, float]

    def as_metadata(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "tier": self.tier,
            "trust_signals": self.trust_signals,
            "community_validated_proxy": self.community_validated_proxy,
            "official_validated": self.official_validated,
            "moderation_verdict": self.moderation_verdict,
            "stats_snapshot": self.stats_snapshot,
        }


def summarize_skill_quality(
    skill: Skill,
    *,
    official_score: float | None = None,
) -> SkillQualitySummary:
    return summarize_skill_quality_inputs(
        stats=skill.stats,
        is_official=skill.is_official,
        risk_level=skill.risk_level,
        tags=skill.tags,
        source_payload=skill.source_payload,
        owner_handle=skill.owner_handle,
        official_score=official_score,
    )


def summarize_skill_quality_inputs(
    *,
    stats: dict[str, Any] | None,
    is_official: bool,
    risk_level: RiskLevel | str,
    tags: list[str] | None,
    source_payload: dict[str, Any] | None,
    owner_handle: str | None = None,
    official_score: float | None = None,
) -> SkillQualitySummary:
    normalized_stats = stats or {}
    stars = _safe_float(normalized_stats.get("stars"))
    downloads = _safe_float(normalized_stats.get("downloads"))
    installs_current = _safe_float(normalized_stats.get("installsCurrent"))
    installs_all_time = _safe_float(normalized_stats.get("installsAllTime"))
    comments = _safe_float(normalized_stats.get("comments"))
    verdict = extract_moderation_verdict(tags=tags, source_payload=source_payload)
    low_risk = _risk_value(risk_level) == RiskLevel.low.value
    suspicious = verdict in SUSPICIOUS_MODERATION_VERDICTS
    moderation_trusted = verdict in TRUSTED_MODERATION_VERDICTS
    official_validated = bool(is_official or str(owner_handle or "").strip().lower() == "openclaw")
    community_feedback = comments >= 1
    community_validated_proxy = (
        not suspicious
        and community_feedback
        and (stars >= 5 or downloads >= 100 or installs_current >= 5 or installs_all_time >= 100)
    )

    score = (
        math.log1p(stars) * 1.8
        + math.log1p(downloads) * 0.9
        + math.log1p(installs_current) * 1.2
        + math.log1p(installs_all_time) * 0.5
        + math.log1p(comments) * 0.9
    )
    if official_validated:
        score += 3.0
    if moderation_trusted:
        score += 1.5
    if low_risk:
        score += 1.0
    if community_validated_proxy:
        score += 2.5
    if official_score is not None:
        score += max(0.0, min(official_score, 5.0)) * 0.8
    if suspicious:
        score -= 10.0

    trust_signals: list[str] = []
    if official_validated:
        trust_signals.append("官方发布者")
    if moderation_trusted and verdict:
        trust_signals.append(f"审核结论={verdict}")
    if community_feedback:
        trust_signals.append(f"社区反馈数={int(comments)}")
    if community_validated_proxy:
        trust_signals.append("社区验证代理信号")
    if stars >= 25:
        trust_signals.append(f"高星标={int(stars)}")
    elif stars >= 5:
        trust_signals.append(f"星标={int(stars)}")
    if downloads >= 5000:
        trust_signals.append(f"高下载量={int(downloads)}")
    elif downloads >= 100:
        trust_signals.append(f"下载量={int(downloads)}")
    if installs_current >= 25:
        trust_signals.append(f"活跃安装={int(installs_current)}")
    if low_risk:
        trust_signals.append("低风险画像")
    if suspicious and verdict:
        trust_signals.append(f"审核风险={verdict}")

    tier = _quality_tier(
        score=score,
        suspicious=suspicious,
        official_validated=official_validated,
        community_validated_proxy=community_validated_proxy,
    )
    return SkillQualitySummary(
        score=round(score, 4),
        tier=tier,
        trust_signals=trust_signals,
        community_validated_proxy=community_validated_proxy,
        official_validated=official_validated,
        moderation_verdict=verdict,
        stats_snapshot={
            "stars": stars,
            "downloads": downloads,
            "installs_current": installs_current,
            "installs_all_time": installs_all_time,
            "comments": comments,
        },
    )


def build_quality_tags(summary: SkillQualitySummary) -> list[str]:
    tags = [f"quality:{summary.tier}"]
    if summary.official_validated:
        tags.append("signal:official-publisher")
    if summary.community_validated_proxy:
        tags.append("signal:community-validated-proxy")
    elif summary.stats_snapshot.get("comments", 0) >= 1:
        tags.append("signal:community-feedback")
    if summary.stats_snapshot.get("stars", 0) >= 25:
        tags.append("signal:high-stars")
    if summary.stats_snapshot.get("downloads", 0) >= 5000:
        tags.append("signal:high-downloads")
    if summary.stats_snapshot.get("installs_current", 0) >= 25:
        tags.append("signal:active-installs")
    if summary.moderation_verdict in TRUSTED_MODERATION_VERDICTS:
        tags.append("signal:trusted-moderation")
    if summary.moderation_verdict in SUSPICIOUS_MODERATION_VERDICTS:
        tags.append("signal:suspicious-moderation")
    return tags


def extract_moderation_verdict(
    *,
    tags: list[str] | None,
    source_payload: dict[str, Any] | None,
) -> str | None:
    for tag in tags or []:
        normalized = str(tag).strip().lower()
        if normalized.startswith("verdict:"):
            _, value = normalized.split(":", 1)
            return value or None

    payload = source_payload or {}
    detail = payload.get("detail")
    if isinstance(detail, dict):
        moderation = detail.get("moderation")
        if isinstance(moderation, dict):
            verdict = str(moderation.get("verdict") or "").strip().lower()
            if verdict:
                return verdict
    return None


def _quality_tier(
    *,
    score: float,
    suspicious: bool,
    official_validated: bool,
    community_validated_proxy: bool,
) -> str:
    if suspicious or score < 0:
        return "avoid"
    if score >= 16 or (official_validated and community_validated_proxy):
        return "trusted"
    if score >= 10:
        return "strong"
    if score >= 5:
        return "emerging"
    return "basic"


def _risk_value(value: RiskLevel | str) -> str:
    if isinstance(value, RiskLevel):
        return value.value
    return str(value or "").strip().lower()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
