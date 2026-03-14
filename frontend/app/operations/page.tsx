"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";
import type { OperatorChangeLog, Skill } from "../lib/types";

type LogFilters = {
  entity_type: string;
  entity_id: string;
  action: string;
  actor: string;
  note_q: string;
  limit: string;
};

const defaultFilters: LogFilters = {
  entity_type: "",
  entity_id: "",
  action: "",
  actor: "",
  note_q: "",
  limit: "80",
};

function securityFocusTitleFromParam(value: string | null) {
  switch (value) {
    case "safe_to_use":
      return "eligible";
    case "use_with_caution":
      return "caution";
    case "manual_review_required":
      return "manual review";
    case "block_or_quarantine":
      return "excluded";
    case "unresolved":
      return "unresolved";
    default:
      return "all";
  }
}

function nodePresetTitleFromParam(value: string | null) {
  switch (value) {
    case "failed_only":
      return "failed only";
    case "failed_high_risk":
      return "failed high risk";
    default:
      return "all nodes";
  }
}

function buildPresetSummary(href: string) {
  const query = href.split("?", 2)[1] ?? "";
  const params = new URLSearchParams(query);
  return [
    params.get("status") || "all statuses",
    params.get("flagged_only") === "1" ? "flagged only" : "all requests",
    securityFocusTitleFromParam(params.get("security_focus")),
    nodePresetTitleFromParam(params.get("node_preset")),
    params.get("request_id") ? `request #${params.get("request_id")}` : "request none",
    params.get("workflow_id") ? `workflow #${params.get("workflow_id")}` : "workflow none",
  ].join(" · ");
}

function buildQuery(filters: LogFilters) {
  const params = new URLSearchParams();
  if (filters.entity_type.trim()) {
    params.set("entity_type", filters.entity_type.trim());
  }
  if (filters.entity_id.trim()) {
    params.set("entity_id", filters.entity_id.trim());
  }
  if (filters.action.trim()) {
    params.set("action", filters.action.trim());
  }
  if (filters.actor.trim()) {
    params.set("actor", filters.actor.trim());
  }
  if (filters.note_q.trim()) {
    params.set("note_q", filters.note_q.trim());
  }
  params.set("limit", filters.limit.trim() || "80");
  return params.toString();
}

function summarizeState(value: Record<string, unknown>) {
  const keys = Object.keys(value || {});
  if (!keys.length) {
    return "empty";
  }
  return keys
    .slice(0, 4)
    .map((key) => `${key}: ${JSON.stringify(value[key])}`)
    .join(" | ");
}

export default function OperationsPage() {
  const [filters, setFilters] = useState<LogFilters>(defaultFilters);
  const [items, setItems] = useState<OperatorChangeLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillItems, setSkillItems] = useState<Skill[]>([]);
  const [copiedPresetHref, setCopiedPresetHref] = useState("");
  const [copiedPresetSummary, setCopiedPresetSummary] = useState("");
  const [error, setError] = useState("");

  async function copyPresetHref(href: string) {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${href}`);
      setCopiedPresetHref(href);
    } catch {
      setCopiedPresetHref("copy_failed");
    }
  }

  async function copyPresetSummary(summary: string) {
    try {
      await navigator.clipboard.writeText(summary);
      setCopiedPresetSummary(summary);
    } catch {
      setCopiedPresetSummary("copy_failed");
    }
  }

  async function loadLogs(nextFilters: LogFilters = filters) {
    setLoading(true);
    setError("");
    try {
      const query = buildQuery(nextFilters);
      const data = await apiFetch<OperatorChangeLog[]>(`/skills/change-logs?${query}`);
      setItems(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadSkillOverview() {
    setSkillsLoading(true);
    setError("");
    try {
      const data = await apiFetch<Skill[]>("/skills/?status=approved&limit=200");
      setSkillItems(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSkillsLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setLoading(true);
      setSkillsLoading(true);
      setError("");
      try {
        const [data, skillData] = await Promise.all([
          apiFetch<OperatorChangeLog[]>(`/skills/change-logs?${buildQuery(defaultFilters)}`),
          apiFetch<Skill[]>("/skills/?status=approved&limit=200"),
        ]);
        if (!cancelled) {
          setItems(data);
          setSkillItems(skillData);
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setSkillsLoading(false);
        }
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadLogs(filters);
  }

  const exportQuery = buildQuery(filters);
  const securitySummary = {
    all: skillItems.length,
    safe_to_use: skillItems.filter((item) => item.security_verdict === "safe_to_use").length,
    use_with_caution: skillItems.filter((item) => item.security_verdict === "use_with_caution").length,
    manual_review_required: skillItems.filter((item) => item.security_verdict === "manual_review_required").length,
    block_or_quarantine: skillItems.filter((item) => item.security_verdict === "block_or_quarantine").length,
    operator_override: skillItems.filter((item) => {
      const metadata = item.registry_metadata ?? {};
      return typeof metadata === "object" && metadata !== null && "security_override" in metadata;
    }).length,
  };

  return (
    <section className="grid" style={{ gap: 20 }}>
      <article className="panel">
        <p className="eyebrow">Operations</p>
        <h2 style={{ marginTop: 0 }}>Unified operator change log</h2>
        <p className="small" style={{ fontSize: 14 }}>
          Search tag curation, search-policy edits, and rollbacks in one place. Export the same
          filtered view as CSV or JSONL.
        </p>
      </article>

      <article className="panel">
        <div className="stack-header">
          <div>
            <p className="eyebrow">Security Overview</p>
            <h2 style={{ marginTop: 0 }}>Cross-console skill safety snapshot</h2>
            <p className="small" style={{ fontSize: 14 }}>
              Jump straight into eligible, cautionary, manual-review, excluded, or operator-overridden skills.
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <span className="small">{skillsLoading ? "loading skills..." : `${skillItems.length} approved skills loaded`}</span>
            <button type="button" className="ghost-button" onClick={() => void loadSkillOverview()}>
              Refresh Skill Snapshot
            </button>
          </div>
        </div>
        <div className="grid grid-2" style={{ marginTop: 14 }}>
          {[
            { key: "all", title: "All Approved", count: securitySummary.all, note: "Current approved-skill pool", href: "/skills" },
            { key: "safe_to_use", title: "Eligible", count: securitySummary.safe_to_use, note: "Default planning can use directly", href: "/skills?security_focus=safe_to_use" },
            { key: "use_with_caution", title: "Caution", count: securitySummary.use_with_caution, note: "Allowed with extra care", href: "/skills?security_focus=use_with_caution" },
            { key: "manual_review_required", title: "Manual Review", count: securitySummary.manual_review_required, note: "Planner de-prioritizes these", href: "/skills?security_focus=manual_review_required" },
            { key: "block_or_quarantine", title: "Excluded", count: securitySummary.block_or_quarantine, note: "Default planning excludes these", href: "/skills?security_focus=block_or_quarantine" },
            { key: "operator_override", title: "Overrides", count: securitySummary.operator_override, note: "Explicit operator decision recorded", href: "/skills?security_focus=operator_override" },
          ].map((card) => (
            <Link
              key={card.key}
              href={card.href}
              className="panel"
              style={{ textDecoration: "none", display: "block", color: "inherit" }}
            >
              <div className="small">{card.title}</div>
              <div style={{ fontSize: 30, fontWeight: 700, margin: "6px 0" }}>{card.count}</div>
              <div className="small">{card.note}</div>
            </Link>
          ))}
        </div>
      </article>

      <article className="panel">
        <div className="stack-header">
          <div>
            <p className="eyebrow">Run Audit Presets</p>
            <h2 style={{ marginTop: 0 }}>Jump straight into risky execution views</h2>
            <p className="small" style={{ fontSize: 14 }}>
              Open a pre-filtered run-audit view for failed executions, high-risk failures, or manual-review bottlenecks.
            </p>
          </div>
        </div>
        <div className="grid grid-3" style={{ marginTop: 14 }}>
          {[
            {
              key: "flagged_requests",
              title: "Flagged Requests",
              note: "Only requests tied to non-eligible or unresolved Skills.",
              href: "/runs?flagged_only=1",
            },
            {
              key: "flagged_failures",
              title: "Flagged Failures",
              note: "Flagged requests already in failed state with high-risk failed nodes.",
              href: "/runs?status=failed&flagged_only=1&node_preset=failed_high_risk",
            },
            {
              key: "failed",
              title: "Failed Runs",
              note: "Only run requests already in failed state.",
              href: "/runs?status=failed&node_preset=failed_only",
            },
            {
              key: "excluded_failed",
              title: "Excluded Failures",
              note: "Failed nodes tied to block_or_quarantine Skills.",
              href: "/runs?status=failed&security_focus=block_or_quarantine&node_preset=failed_high_risk",
            },
            {
              key: "manual_review_failed",
              title: "Manual Review Failures",
              note: "Failed nodes that still require manual review.",
              href: "/runs?status=failed&security_focus=manual_review_required&node_preset=failed_high_risk",
            },
          ].map((card) => {
            const summary = buildPresetSummary(card.href);
            return (
            <div key={card.key} className="panel">
              <div className="small">{card.title}</div>
              <div style={{ fontSize: 18, fontWeight: 700, margin: "6px 0" }}>Open Preset</div>
              <div className="small">{card.note}</div>
              <pre className="code" style={{ marginTop: 10 }}>{summary}</pre>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
                <Link href={card.href}>Open View</Link>
                <button type="button" className="ghost-button" onClick={() => void copyPresetHref(card.href)}>
                  Copy Link
                </button>
                <button type="button" className="ghost-button" onClick={() => void copyPresetSummary(summary)}>
                  Copy Summary
                </button>
                {copiedPresetHref === card.href ? <span className="small">Copied</span> : null}
                {copiedPresetHref === "copy_failed" ? <span className="small">Copy failed</span> : null}
                {copiedPresetSummary === summary ? <span className="small">Summary copied</span> : null}
                {copiedPresetSummary === "copy_failed" ? <span className="small">Summary copy failed</span> : null}
              </div>
            </div>
          );
          })}
        </div>
      </article>

      <article className="panel">
        <form className="grid" style={{ gap: 12 }} onSubmit={handleSubmit}>
          <div className="grid grid-3">
            <input
              value={filters.entity_type}
              onChange={(event) => setFilters((prev) => ({ ...prev, entity_type: event.target.value }))}
              placeholder="entity_type: search_policy_rule"
            />
            <input
              value={filters.entity_id}
              onChange={(event) => setFilters((prev) => ({ ...prev, entity_id: event.target.value }))}
              placeholder="entity_id"
            />
            <input
              value={filters.action}
              onChange={(event) => setFilters((prev) => ({ ...prev, action: event.target.value }))}
              placeholder="action: rollback_search_policy_rule"
            />
          </div>
          <div className="grid grid-3">
            <input
              value={filters.actor}
              onChange={(event) => setFilters((prev) => ({ ...prev, actor: event.target.value }))}
              placeholder="actor: skills-console"
            />
            <input
              value={filters.note_q}
              onChange={(event) => setFilters((prev) => ({ ...prev, note_q: event.target.value }))}
              placeholder="note contains..."
            />
            <input
              value={filters.limit}
              onChange={(event) => setFilters((prev) => ({ ...prev, limit: event.target.value }))}
              placeholder="limit"
            />
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button type="submit">Load Logs</button>
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                setFilters(defaultFilters);
                void loadLogs(defaultFilters);
              }}
            >
              Reset
            </button>
            <a className="ghost-button" href={`/api/backend/skills/change-logs/export?format=csv&${exportQuery}`}>
              Export CSV
            </a>
            <a className="ghost-button" href={`/api/backend/skills/change-logs/export?format=jsonl&${exportQuery}`}>
              Export JSONL
            </a>
          </div>
        </form>
      </article>

      <article className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>Change events</h3>
          <span className="small">{loading ? "loading..." : `${items.length} entries`}</span>
        </div>
        {error ? (
          <p className="small" style={{ color: "#b42318" }}>
            {error}
          </p>
        ) : null}
        <div className="grid" style={{ gap: 12, marginTop: 16 }}>
          {items.map((item) => (
            <article key={item.id} className="panel" style={{ background: "#fffaf0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <strong>
                  {item.entity_type} #{item.entity_id}
                </strong>
                <span className="small">
                  {item.actor} · {new Date(item.created_at).toLocaleString()}
                </span>
              </div>
              <p className="small" style={{ marginTop: 8 }}>
                action: <code>{item.action}</code>
              </p>
              <p className="small">{item.note || "No note provided."}</p>
              <p className="small">before: {summarizeState(item.before_state)}</p>
              <p className="small">after: {summarizeState(item.after_state)}</p>
            </article>
          ))}
          {!items.length && !loading ? (
            <article className="panel" style={{ background: "#fffaf0" }}>
              <p className="small">No operator changes matched the current filters.</p>
            </article>
          ) : null}
        </div>
      </article>
    </section>
  );
}
