from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.models.common import ExecutionMode, RiskLevel
from app.models.skill import Skill
from app.services.skill_quality import SUSPICIOUS_MODERATION_VERDICTS, TRUSTED_MODERATION_VERDICTS, extract_moderation_verdict

SHELL_KEYWORDS = {
    "bash",
    "cli",
    "cmd",
    "command",
    "exec",
    "execute",
    "git",
    "powershell",
    "script",
    "shell",
    "terminal",
}
NETWORK_KEYWORDS = {
    "api",
    "browser",
    "crawl",
    "curl",
    "discord",
    "endpoint",
    "fetch",
    "http",
    "https",
    "request",
    "scrape",
    "search",
    "slack",
    "telegram",
    "web",
    "webhook",
    "wget",
}
FILE_KEYWORDS = {
    "csv",
    "docs",
    "document",
    "drive",
    "excel",
    "file",
    "folder",
    "local",
    "notion",
    "pdf",
    "sheet",
    "storage",
    "upload",
    "write",
}
CREDENTIAL_KEYWORDS = {
    ".env",
    "api key",
    "apikey",
    "aws",
    "cookie",
    "credential",
    "oauth",
    "password",
    "secret",
    "session",
    "ssh",
    "token",
}
DYNAMIC_EXECUTION_KEYWORDS = {
    "base64",
    "decode",
    "dynamic code",
    "eval",
    "exec(",
    "minified",
    "obfuscated",
}
SYSTEM_MUTATION_KEYWORDS = {
    "apt",
    "brew",
    "global install",
    "install package",
    "npm install",
    "pip install",
    "registry write",
    "root access",
    "sudo",
    "system config",
}
SENSITIVE_PATH_KEYWORDS = {
    "~/.aws",
    "~/.config",
    "~/.ssh",
    "browser cookie",
    "identity.md",
    "memory.md",
    "soul.md",
    "user.md",
}


@dataclass(slots=True)
class SkillSecuritySummary:
    score: float
    tier: str
    verdict: str
    flags: list[str]
    permission_profile: dict[str, bool]
    moderation_verdict: str | None
    operator_override: dict[str, Any] | None = None

    def as_metadata(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "tier": self.tier,
            "verdict": self.verdict,
            "flags": self.flags,
            "permission_profile": self.permission_profile,
            "moderation_verdict": self.moderation_verdict,
            "operator_override": self.operator_override,
        }


def summarize_skill_security(skill: Skill) -> SkillSecuritySummary:
    return summarize_skill_security_inputs(
        name=skill.name,
        display_name=skill.display_name,
        category=skill.category,
        description=skill.description,
        summary=skill.summary,
        tags=skill.tags,
        execution_mode=skill.execution_mode,
        read_only=skill.read_only,
        writes_external_state=skill.writes_external_state,
        risk_level=skill.risk_level,
        source_payload=skill.source_payload,
        owner_handle=skill.owner_handle,
        registry_metadata=skill.registry_metadata,
    )


def summarize_skill_security_inputs(
    *,
    name: str,
    display_name: str,
    category: str,
    description: str,
    summary: str,
    tags: list[str] | None,
    execution_mode: ExecutionMode | str,
    read_only: bool,
    writes_external_state: bool,
    risk_level: RiskLevel | str,
    source_payload: dict[str, Any] | None,
    owner_handle: str | None = None,
    registry_metadata: dict[str, Any] | None = None,
) -> SkillSecuritySummary:
    text = " ".join(
        [
            name or "",
            display_name or "",
            category or "",
            description or "",
            summary or "",
            " ".join(str(tag) for tag in (tags or [])),
        ]
    ).lower()
    moderation_verdict = extract_moderation_verdict(tags=tags, source_payload=source_payload)
    official_owner = str(owner_handle or "").strip().lower() == "openclaw"

    permission_profile = {
        "network_access": _contains_any(text, NETWORK_KEYWORDS) or category in {"communication", "data", "web"},
        "file_access": _contains_any(text, FILE_KEYWORDS) or not read_only,
        "command_execution": _contains_any(text, SHELL_KEYWORDS) or category == "developer",
        "credential_access": _contains_any(text, CREDENTIAL_KEYWORDS),
        "external_write": bool(writes_external_state),
    }

    flags: list[str] = []
    if permission_profile["credential_access"]:
        flags.append("涉及凭据或令牌访问")
    if permission_profile["command_execution"]:
        flags.append("涉及 shell/命令执行")
    if _contains_any(text, SENSITIVE_PATH_KEYWORDS):
        flags.append("涉及敏感配置或身份文件")
    if _contains_any(text, DYNAMIC_EXECUTION_KEYWORDS):
        flags.append("涉及动态执行或编码内容")
    if _contains_any(text, SYSTEM_MUTATION_KEYWORDS):
        flags.append("涉及系统级安装或配置修改")
    if permission_profile["external_write"]:
        flags.append("具备外部状态写入能力")
    if moderation_verdict in SUSPICIOUS_MODERATION_VERDICTS:
        flags.append(f"审核结论={moderation_verdict}")

    score = 100.0
    if _risk_value(risk_level) == RiskLevel.high.value:
        score -= 35.0
    elif _risk_value(risk_level) == RiskLevel.medium.value:
        score -= 15.0

    if permission_profile["network_access"]:
        score -= 6.0
    if permission_profile["file_access"]:
        score -= 6.0
    if permission_profile["command_execution"]:
        score -= 22.0
    if permission_profile["credential_access"]:
        score -= 26.0
    if permission_profile["external_write"]:
        score -= 12.0
    if any("敏感配置" in flag for flag in flags):
        score -= 24.0
    if any("动态执行" in flag for flag in flags):
        score -= 24.0
    if any("系统级安装" in flag for flag in flags):
        score -= 24.0
    if moderation_verdict in SUSPICIOUS_MODERATION_VERDICTS:
        score -= 30.0
    if moderation_verdict in TRUSTED_MODERATION_VERDICTS:
        score += 8.0
    if official_owner:
        score += 5.0
    if read_only and _risk_value(risk_level) == RiskLevel.low.value:
        score += 6.0
    if _execution_mode_value(execution_mode) == ExecutionMode.remote.value:
        score -= 2.0

    score = max(0.0, min(100.0, score))
    tier = _security_tier(score=score, moderation_verdict=moderation_verdict)
    verdict = _security_verdict(tier)
    operator_override = extract_security_override(registry_metadata)
    if operator_override:
        verdict = str(operator_override.get("decision") or verdict)
        tier = _tier_for_override_decision(verdict)
        score = _score_for_override_tier(score, tier)
        flags = [f"人工安全复核={verdict}", *flags]

    if not flags and tier == "safe":
        flags.append("未发现明显安全红旗")
    elif not flags and tier == "caution":
        flags.append("需要按权限范围谨慎使用")

    return SkillSecuritySummary(
        score=round(score, 4),
        tier=tier,
        verdict=verdict,
        flags=flags,
        permission_profile=permission_profile,
        moderation_verdict=moderation_verdict,
        operator_override=operator_override,
    )


def build_security_tags(summary: SkillSecuritySummary) -> list[str]:
    tags = [f"security:{summary.tier}", f"security-verdict:{summary.verdict}"]
    profile = summary.permission_profile
    if profile.get("network_access"):
        tags.append("security-signal:network-access")
    if profile.get("file_access"):
        tags.append("security-signal:file-access")
    if profile.get("command_execution"):
        tags.append("security-signal:command-execution")
    if profile.get("credential_access"):
        tags.append("security-signal:credential-access")
    if profile.get("external_write"):
        tags.append("security-signal:external-write")
    if summary.moderation_verdict in SUSPICIOUS_MODERATION_VERDICTS:
        tags.append("security-signal:suspicious-moderation")
    if any("动态执行" in flag for flag in summary.flags):
        tags.append("security-signal:dynamic-execution")
    if any("敏感配置" in flag for flag in summary.flags):
        tags.append("security-signal:sensitive-paths")
    if summary.operator_override:
        tags.append("security-signal:operator-reviewed")
    return tags


def extract_security_override(registry_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    metadata = registry_metadata or {}
    raw = metadata.get("security_override")
    if not isinstance(raw, dict):
        return None
    decision = str(raw.get("decision") or "").strip()
    if decision not in {
        "safe_to_use",
        "use_with_caution",
        "manual_review_required",
        "block_or_quarantine",
    }:
        return None
    normalized = {
        "decision": decision,
        "actor": str(raw.get("actor") or "").strip() or None,
        "note": str(raw.get("note") or "").strip() or None,
        "updated_at": _normalize_datetime_string(raw.get("updated_at")),
    }
    return normalized


def write_security_override(
    registry_metadata: dict[str, Any] | None,
    *,
    decision: str,
    actor: str | None,
    note: str | None,
) -> dict[str, Any]:
    metadata = dict(registry_metadata or {})
    if decision == "clear_override":
        metadata.pop("security_override", None)
        return metadata

    metadata["security_override"] = {
        "decision": decision,
        "actor": str(actor or "").strip() or None,
        "note": str(note or "").strip() or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return metadata


def replace_security_tags(existing_tags: list[str] | None, summary: SkillSecuritySummary) -> list[str]:
    tags = [
        tag
        for tag in (existing_tags or [])
        if not (
            str(tag).startswith("security:")
            or str(tag).startswith("security-verdict:")
            or str(tag).startswith("security-signal:")
        )
    ]
    tags.extend(build_security_tags(summary))
    return sorted(dict.fromkeys(tags))


def _security_tier(*, score: float, moderation_verdict: str | None) -> str:
    if moderation_verdict in SUSPICIOUS_MODERATION_VERDICTS or score < 35:
        return "block"
    if score < 60:
        return "review"
    if score < 82:
        return "caution"
    return "safe"


def _security_verdict(tier: str) -> str:
    if tier == "safe":
        return "safe_to_use"
    if tier == "caution":
        return "use_with_caution"
    if tier == "review":
        return "manual_review_required"
    return "block_or_quarantine"


def _tier_for_override_decision(decision: str) -> str:
    mapping = {
        "safe_to_use": "safe",
        "use_with_caution": "caution",
        "manual_review_required": "review",
        "block_or_quarantine": "block",
    }
    return mapping.get(decision, "review")


def _score_for_override_tier(score: float, tier: str) -> float:
    if tier == "safe":
        return max(score, 90.0)
    if tier == "caution":
        return min(max(score, 60.0), 81.9)
    if tier == "review":
        return min(max(score, 35.0), 59.9)
    return min(score, 20.0)


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _risk_value(value: RiskLevel | str) -> str:
    if isinstance(value, RiskLevel):
        return value.value
    return str(value or "").strip().lower()


def _execution_mode_value(value: ExecutionMode | str) -> str:
    if isinstance(value, ExecutionMode):
        return value.value
    return str(value or "").strip().lower()


def _normalize_datetime_string(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text
