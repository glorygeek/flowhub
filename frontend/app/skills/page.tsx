"use client";

import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "../lib/api";
import {
  OperatorChangeLog,
  SearchPolicyRule,
  ReviewStatus,
  RiskLevel,
  Skill,
  SkillLinkedTag,
  SkillSecurityReview,
  SkillSearchResult,
  SkillTag
} from "../lib/types";

const statusOptions: ReviewStatus[] = ["draft", "pending", "approved", "rejected", "archived"];
const riskOptions: RiskLevel[] = ["low", "medium", "high"];

type CatalogFilters = {
  name: string;
  source: string;
  category: string;
  risk_level: "" | RiskLevel;
  status: "" | ReviewStatus;
};

type SecurityFocus =
  | "all"
  | "safe_to_use"
  | "use_with_caution"
  | "manual_review_required"
  | "block_or_quarantine"
  | "operator_override";

const defaultCatalogFilters: CatalogFilters = {
  name: "",
  source: "",
  category: "",
  risk_level: "",
  status: "approved"
};

function formatNumber(value: unknown) {
  if (typeof value === "number") {
    return Intl.NumberFormat("en-US").format(value);
  }
  return "0";
}

function buildSkillPath(filters: CatalogFilters, selectedTags: string[]) {
  const params = new URLSearchParams();
  if (filters.name.trim()) {
    params.set("name", filters.name.trim());
  }
  if (filters.source.trim()) {
    params.set("source", filters.source.trim());
  }
  if (filters.category.trim()) {
    params.set("category", filters.category.trim());
  }
  if (filters.risk_level) {
    params.set("risk_level", filters.risk_level);
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (selectedTags.length) {
    params.set("tags", selectedTags.join(","));
  }
  params.set("limit", "120");
  return `/skills/?${params.toString()}`;
}

function buildTagPath(query: string, category: string) {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  if (category.trim()) {
    params.set("category", category.trim());
  }
  params.set("limit", "80");
  return `/skills/tags?${params.toString()}`;
}

function buildHistoryQuery(actor: string, noteQuery: string) {
  const params = new URLSearchParams();
  if (actor.trim()) {
    params.set("actor", actor.trim());
  }
  if (noteQuery.trim()) {
    params.set("note_q", noteQuery.trim());
  }
  params.set("limit", "50");
  return params.toString();
}

function QualityBadge({ tier }: { tier: string }) {
  const palette =
    tier === "trusted"
      ? { background: "#d7ecef", color: "#155e75" }
      : tier === "strong"
        ? { background: "#ecf2d2", color: "#4a5b0f" }
        : { background: "#efe6d4", color: "#8b5a2b" };

  return (
    <span
      className="chip"
      style={{ background: palette.background, color: palette.color, borderColor: palette.background }}
    >
      {tier}
    </span>
  );
}

function SecurityBadge({ tier }: { tier: string }) {
  const palette =
    tier === "safe"
      ? { background: "#d9f3e4", color: "#166534" }
      : tier === "caution"
        ? { background: "#fff0c2", color: "#92400e" }
        : tier === "review"
          ? { background: "#ffe2c4", color: "#9a3412" }
          : { background: "#ffd6d6", color: "#991b1b" };

  return (
    <span
      className="chip"
      style={{ background: palette.background, color: palette.color, borderColor: palette.background }}
    >
      security {tier}
    </span>
  );
}

function securityPlanningNote(verdict: string) {
  if (verdict === "block_or_quarantine") {
    return "Default planning: excluded";
  }
  if (verdict === "manual_review_required") {
    return "Default planning: manual review required";
  }
  if (verdict === "use_with_caution") {
    return "Default planning: allowed with caution";
  }
  return "Default planning: eligible";
}

function hasOperatorOverride(skill: Skill) {
  const metadata = skill.registry_metadata ?? {};
  return typeof metadata === "object" && metadata !== null && "security_override" in metadata;
}

function matchesSecurityFocus(skill: Skill, focus: SecurityFocus) {
  if (focus === "all") {
    return true;
  }
  if (focus === "operator_override") {
    return hasOperatorOverride(skill);
  }
  return skill.security_verdict === focus;
}

function securityFocusLabel(focus: SecurityFocus) {
  switch (focus) {
    case "safe_to_use":
      return "Eligible";
    case "use_with_caution":
      return "Caution";
    case "manual_review_required":
      return "Manual Review";
    case "block_or_quarantine":
      return "Excluded";
    case "operator_override":
      return "Overrides";
    default:
      return "All";
  }
}

function parseSecurityFocus(value: string | null): SecurityFocus {
  if (
    value === "safe_to_use" ||
    value === "use_with_caution" ||
    value === "manual_review_required" ||
    value === "block_or_quarantine" ||
    value === "operator_override"
  ) {
    return value;
  }
  return "all";
}

function parseCatalogFiltersFromSearch(params: URLSearchParams): CatalogFilters {
  const riskLevel = params.get("risk_level");
  const status = params.get("status");
  return {
    name: params.get("name") ?? "",
    source: params.get("source") ?? "",
    category: params.get("category") ?? "",
    risk_level: riskLevel === "low" || riskLevel === "medium" || riskLevel === "high" ? riskLevel : "",
    status:
      status === "draft" || status === "pending" || status === "approved" || status === "rejected" || status === "archived"
        ? status
        : defaultCatalogFilters.status,
  };
}

export default function SkillsPage() {
  const [items, setItems] = useState<Skill[]>([]);
  const [tagItems, setTagItems] = useState<SkillTag[]>([]);
  const [policyItems, setPolicyItems] = useState<SearchPolicyRule[]>([]);
  const [searchResults, setSearchResults] = useState<SkillSearchResult[]>([]);
  const [curatedSkillId, setCuratedSkillId] = useState<number | null>(null);
  const [curatedSkillTags, setCuratedSkillTags] = useState<SkillLinkedTag[]>([]);
  const [curatedSkillHistory, setCuratedSkillHistory] = useState<OperatorChangeLog[]>([]);
  const [curatedSecurityReview, setCuratedSecurityReview] = useState<SkillSecurityReview | null>(null);
  const [curatedSecurityHistory, setCuratedSecurityHistory] = useState<OperatorChangeLog[]>([]);
  const [operatorTagDraft, setOperatorTagDraft] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tagsLoading, setTagsLoading] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [curationLoading, setCurationLoading] = useState(false);
  const [curationSaving, setCurationSaving] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [securityLoading, setSecurityLoading] = useState(false);
  const [securitySaving, setSecuritySaving] = useState(false);
  const [policySavingId, setPolicySavingId] = useState<number | null>(null);
  const [securityFocus, setSecurityFocus] = useState<SecurityFocus>("all");
  const [catalogFilters, setCatalogFilters] = useState<CatalogFilters>(defaultCatalogFilters);
  const [tagQuery, setTagQuery] = useState("");
  const [tagCategory, setTagCategory] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>(["quality:trusted"]);
  const [searchQuery, setSearchQuery] = useState("A股 股票 分析 markdown");
  const [policyDrafts, setPolicyDrafts] = useState<
    Record<number, { score_delta: string; priority: string; change_note: string }>
  >({});
  const [policyHistory, setPolicyHistory] = useState<Record<number, OperatorChangeLog[]>>({});
  const [curationNote, setCurationNote] = useState("");
  const [securityDecisionDraft, setSecurityDecisionDraft] = useState("use_with_caution");
  const [securityNote, setSecurityNote] = useState("");
  const [skillHistoryActorFilter, setSkillHistoryActorFilter] = useState("");
  const [skillHistoryNoteFilter, setSkillHistoryNoteFilter] = useState("");
  const [securityHistoryActorFilter, setSecurityHistoryActorFilter] = useState("");
  const [securityHistoryNoteFilter, setSecurityHistoryNoteFilter] = useState("");
  const [policyHistoryActorFilter, setPolicyHistoryActorFilter] = useState("");
  const [policyHistoryNoteFilter, setPolicyHistoryNoteFilter] = useState("");
  const [form, setForm] = useState({
    name: "",
    display_name: "",
    source: "manual",
    category: "",
    description: "",
    risk_level: "low" as RiskLevel,
    status: "draft" as ReviewStatus
  });

  const curatedSkill = items.find((item) => item.id === curatedSkillId) ?? null;
  const visibleItems = items.filter((item) => matchesSecurityFocus(item, securityFocus));
  const securitySummary = {
    all: items.length,
    safe_to_use: items.filter((item) => item.security_verdict === "safe_to_use").length,
    use_with_caution: items.filter((item) => item.security_verdict === "use_with_caution").length,
    manual_review_required: items.filter((item) => item.security_verdict === "manual_review_required").length,
    block_or_quarantine: items.filter((item) => item.security_verdict === "block_or_quarantine").length,
    operator_override: items.filter((item) => hasOperatorOverride(item)).length
  };

  async function loadSkills(filters: CatalogFilters = catalogFilters, tags: string[] = selectedTags) {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<Skill[]>(buildSkillPath(filters, tags));
      setItems(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadTags(query: string = tagQuery, category: string = tagCategory) {
    setTagsLoading(true);
    setError("");
    try {
      const data = await apiFetch<SkillTag[]>(buildTagPath(query, category));
      setTagItems(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setTagsLoading(false);
    }
  }

  async function loadPolicies() {
    setPolicyLoading(true);
    setError("");
    try {
      const data = await apiFetch<SearchPolicyRule[]>("/skills/search/policies");
      setPolicyItems(data);
      setPolicyDrafts(
        Object.fromEntries(
          data.map((item) => [
            item.id,
            {
              score_delta: String(item.score_delta),
              priority: String(item.priority),
              change_note: policyDrafts[item.id]?.change_note || ""
            }
          ])
        )
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPolicyLoading(false);
    }
  }

  async function loadSkillTagLinks(skillId: number) {
    setCurationLoading(true);
    setError("");
    try {
      const data = await apiFetch<SkillLinkedTag[]>(`/skills/${skillId}/tags`);
      setCuratedSkillId(skillId);
      setCuratedSkillTags(data);
      setOperatorTagDraft(
        data
          .filter((item) => item.link_source === "operator")
          .map((item) => item.name)
          .join(", ")
      );
      void loadSkillTagHistory(skillId);
      void loadSecurityReview(skillId);
      void loadSecurityHistory(skillId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCurationLoading(false);
    }
  }

  async function loadSkillTagHistory(skillId: number) {
    setHistoryLoading(true);
    setError("");
    try {
      const query = buildHistoryQuery(skillHistoryActorFilter, skillHistoryNoteFilter);
      const data = await apiFetch<OperatorChangeLog[]>(`/skills/${skillId}/tag-history?${query}`);
      setCuratedSkillHistory(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadSecurityReview(skillId: number) {
    setSecurityLoading(true);
    setError("");
    try {
      const data = await apiFetch<SkillSecurityReview>(`/skills/${skillId}/security-review`);
      setCuratedSecurityReview(data);
      setSecurityDecisionDraft(data.operator_override?.decision || data.security_verdict || "use_with_caution");
      setSecurityNote(data.operator_override?.note || "");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSecurityLoading(false);
    }
  }

  async function loadSecurityHistory(skillId: number) {
    setError("");
    try {
      const query = buildHistoryQuery(securityHistoryActorFilter, securityHistoryNoteFilter);
      const data = await apiFetch<OperatorChangeLog[]>(`/skills/${skillId}/security-history?${query}`);
      setCuratedSecurityHistory(data);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function loadPolicyHistory(ruleId: number) {
    setError("");
    try {
      const query = buildHistoryQuery(policyHistoryActorFilter, policyHistoryNoteFilter);
      const data = await apiFetch<OperatorChangeLog[]>(`/skills/search/policies/${ruleId}/history?${query}`);
      setPolicyHistory((prev) => ({ ...prev, [ruleId]: data }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function runSearch(query: string = searchQuery) {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }

    setSearchLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ q: query.trim(), limit: "8" });
      const data = await apiFetch<SkillSearchResult[]>(`/skills/search?${params.toString()}`);
      setSearchResults(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSearchLoading(false);
    }
  }

  async function createSkill(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await apiFetch<Skill>("/skills/", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          tags: [],
          input_schema: {},
          output_schema: {},
          execution_mode: "local",
          read_only: false,
          writes_external_state: false,
          is_official: false,
          version: "1.0.0",
          summary: ""
        })
      });
      setForm({
        name: "",
        display_name: "",
        source: "manual",
        category: "",
        description: "",
        risk_level: "low",
        status: "draft"
      });
      await Promise.all([loadSkills(), loadTags()]);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function updateStatus(id: number, status: ReviewStatus, riskLevel: RiskLevel) {
    setError("");
    try {
      await apiFetch<Skill>(`/skills/${id}`, {
        method: "PUT",
        body: JSON.stringify({ status, risk_level: riskLevel })
      });
      await loadSkills();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function removeSkill(id: number) {
    setError("");
    try {
      await apiFetch(`/skills/${id}`, { method: "DELETE" });
      if (curatedSkillId === id) {
        setCuratedSkillId(null);
        setCuratedSkillTags([]);
        setCuratedSkillHistory([]);
        setCuratedSecurityReview(null);
        setCuratedSecurityHistory([]);
        setOperatorTagDraft("");
        setCurationNote("");
        setSecurityDecisionDraft("use_with_caution");
        setSecurityNote("");
      }
      await Promise.all([loadSkills(), loadTags()]);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function saveOperatorTags() {
    if (!curatedSkillId) {
      return;
    }
    setCurationSaving(true);
    setError("");
    try {
      const tagNames = operatorTagDraft
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const data = await apiFetch<SkillLinkedTag[]>(`/skills/${curatedSkillId}/tags`, {
        method: "PUT",
        body: JSON.stringify({
          tag_names: tagNames,
          change_note: curationNote || undefined,
          actor: "skills-console"
        })
      });
      setCuratedSkillTags(data);
      setOperatorTagDraft(
        data
          .filter((item) => item.link_source === "operator")
          .map((item) => item.name)
          .join(", ")
      );
      setCurationNote("");
      await loadSkillTagHistory(curatedSkillId);
      await Promise.all([loadTags(), loadSkills()]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCurationSaving(false);
    }
  }

  async function saveSecurityReview() {
    if (!curatedSkillId) {
      return;
    }
    setSecuritySaving(true);
    setError("");
    try {
      const data = await apiFetch<SkillSecurityReview>(`/skills/${curatedSkillId}/security-review`, {
        method: "PUT",
        body: JSON.stringify({
          decision: securityDecisionDraft,
          change_note: securityNote || undefined,
          actor: "skills-console"
        })
      });
      setCuratedSecurityReview(data);
      setSecurityDecisionDraft(data.operator_override?.decision || data.security_verdict || "use_with_caution");
      setSecurityNote(data.operator_override?.note || "");
      await loadSecurityHistory(curatedSkillId);
      await Promise.all([loadSkills(), loadTags(), runSearch()]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSecuritySaving(false);
    }
  }

  async function clearSecurityOverride() {
    if (!curatedSkillId) {
      return;
    }
    setSecuritySaving(true);
    setError("");
    try {
      const data = await apiFetch<SkillSecurityReview>(`/skills/${curatedSkillId}/security-review`, {
        method: "PUT",
        body: JSON.stringify({
          decision: "clear_override",
          change_note: securityNote || undefined,
          actor: "skills-console"
        })
      });
      setCuratedSecurityReview(data);
      setSecurityDecisionDraft(data.operator_override?.decision || data.security_verdict || "use_with_caution");
      setSecurityNote("");
      await loadSecurityHistory(curatedSkillId);
      await Promise.all([loadSkills(), loadTags(), runSearch()]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSecuritySaving(false);
    }
  }

  async function toggleTagDefinition(tag: SkillTag | SkillLinkedTag, note?: string) {
    setError("");
    try {
      await apiFetch<SkillTag>(`/skills/tags/${tag.id}`, {
        method: "PUT",
        body: JSON.stringify({
          active: !tag.active,
          change_note: note || undefined,
          actor: "skills-console"
        })
      });
      await loadTags();
      if (curatedSkillId) {
        await Promise.all([
          loadSkillTagLinks(curatedSkillId),
          loadSkillTagHistory(curatedSkillId),
          loadSecurityReview(curatedSkillId),
          loadSecurityHistory(curatedSkillId)
        ]);
      }
      await loadSkills();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function savePolicyRule(rule: SearchPolicyRule, activeOverride?: boolean) {
    const draft = policyDrafts[rule.id] ?? {
      score_delta: String(rule.score_delta),
      priority: String(rule.priority),
      change_note: ""
    };
    setPolicySavingId(rule.id);
    setError("");
    try {
      await apiFetch<SearchPolicyRule>(`/skills/search/policies/${rule.id}`, {
        method: "PUT",
        body: JSON.stringify({
          active: typeof activeOverride === "boolean" ? activeOverride : rule.active,
          score_delta: Number(draft.score_delta),
          priority: Number(draft.priority),
          change_note: draft.change_note || undefined,
          actor: "skills-console"
        })
      });
      await loadPolicies();
      await loadPolicyHistory(rule.id);
      setPolicyDrafts((prev) => ({
        ...prev,
        [rule.id]: { ...draft, change_note: "" }
      }));
      await runSearch();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPolicySavingId(null);
    }
  }

  async function rollbackPolicyRule(rule: SearchPolicyRule, logId: number) {
    const draft = policyDrafts[rule.id] ?? {
      score_delta: String(rule.score_delta),
      priority: String(rule.priority),
      change_note: ""
    };
    setPolicySavingId(rule.id);
    setError("");
    try {
      await apiFetch<SearchPolicyRule>(`/skills/search/policies/${rule.id}/rollback/${logId}`, {
        method: "POST",
        body: JSON.stringify({
          change_note: draft.change_note || undefined,
          actor: "skills-console"
        })
      });
      await loadPolicies();
      await loadPolicyHistory(rule.id);
      await runSearch();
      setPolicyDrafts((prev) => ({
        ...prev,
        [rule.id]: { ...draft, change_note: "" }
      }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPolicySavingId(null);
    }
  }

  function toggleTag(tagName: string) {
    setSelectedTags((prev) =>
      prev.includes(tagName) ? prev.filter((item) => item !== tagName) : [...prev, tagName]
    );
  }

  function addOperatorTag(tagName: string) {
    const existing = operatorTagDraft
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (existing.includes(tagName)) {
      return;
    }
    setOperatorTagDraft(existing.length ? `${existing.join(", ")}, ${tagName}` : tagName);
  }

  async function applyCatalogFilters(e?: FormEvent) {
    e?.preventDefault();
    await loadSkills();
  }

  async function resetCatalogFilters() {
    const nextTags: string[] = [];
    setCatalogFilters(defaultCatalogFilters);
    setSelectedTags(nextTags);
    await loadSkills(defaultCatalogFilters, nextTags);
  }

  async function submitSearch(e: FormEvent) {
    e.preventDefault();
    await runSearch();
  }

  async function refreshTags(e: FormEvent) {
    e.preventDefault();
    await loadTags();
  }

  useEffect(() => {
    const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : new URLSearchParams();
    const nextFocus = parseSecurityFocus(params.get("security_focus"));
    const nextFilters = parseCatalogFiltersFromSearch(params);
    const nextTags = params.get("tags")
      ? params
          .get("tags")!
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean)
      : nextFocus === "all"
        ? ["quality:trusted"]
        : [];
    setCatalogFilters(nextFilters);
    setSecurityFocus(nextFocus);
    setSelectedTags(nextTags);
    void Promise.all([loadSkills(nextFilters, nextTags), loadTags(), loadPolicies(), runSearch()]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="grid" style={{ gap: 18 }}>
      <article className="panel">
        <div className="stack-header">
          <div>
            <p className="eyebrow">Skill Catalog Console</p>
            <h2 style={{ margin: "6px 0 8px" }}>Search, filter, and curate trusted skills</h2>
            <p className="small" style={{ fontSize: 14 }}>
              This surface combines the local tag library, quality signals, quick search ranking,
              and operator tag curation in one place.
            </p>
          </div>
          <div className="subpanel" style={{ minWidth: 240 }}>
            <strong>{visibleItems.length}</strong>
            <div className="small">
              catalog entries in current view
              {securityFocus !== "all" ? ` · ${securityFocusLabel(securityFocus)}` : ""}
            </div>
            <div style={{ height: 10 }} />
            <strong>{tagItems.length}</strong>
            <div className="small">indexed tags loaded</div>
          </div>
        </div>
        {error ? (
          <p className="small" style={{ color: "#9f1239" }}>
            {error}
          </p>
        ) : null}
      </article>

      <section className="grid grid-2">
        <article className="panel">
          <h3 style={{ marginTop: 0 }}>Catalog Filters</h3>
          <form className="grid" onSubmit={applyCatalogFilters}>
            <div className="grid grid-2">
              <input
                placeholder="name contains..."
                value={catalogFilters.name}
                onChange={(e) => setCatalogFilters((prev) => ({ ...prev, name: e.target.value }))}
              />
              <input
                placeholder="source"
                value={catalogFilters.source}
                onChange={(e) => setCatalogFilters((prev) => ({ ...prev, source: e.target.value }))}
              />
              <input
                placeholder="category"
                value={catalogFilters.category}
                onChange={(e) => setCatalogFilters((prev) => ({ ...prev, category: e.target.value }))}
              />
              <select
                value={catalogFilters.risk_level}
                onChange={(e) =>
                  setCatalogFilters((prev) => ({
                    ...prev,
                    risk_level: e.target.value as CatalogFilters["risk_level"]
                  }))
                }
              >
                <option value="">all risk levels</option>
                {riskOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <select
                value={catalogFilters.status}
                onChange={(e) =>
                  setCatalogFilters((prev) => ({ ...prev, status: e.target.value as CatalogFilters["status"] }))
                }
              >
                <option value="">all review states</option>
                {statusOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>

            <div className="subpanel">
              <div className="stack-header" style={{ marginBottom: 10 }}>
                <strong>Selected Tags</strong>
                <span className="small">{selectedTags.length} active</span>
              </div>
              <div className="chip-row">
                {selectedTags.length ? (
                  selectedTags.map((tag) => (
                    <button key={tag} type="button" className="chip active-chip" onClick={() => toggleTag(tag)}>
                      {tag}
                    </button>
                  ))
                ) : (
                  <span className="small">No tag filters selected.</span>
                )}
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button type="submit" disabled={loading}>
                {loading ? "Refreshing..." : "Apply Filters"}
              </button>
              <button type="button" className="secondary" onClick={() => void resetCatalogFilters()}>
                Reset
              </button>
            </div>
          </form>
        </article>

        <article className="panel">
          <h3 style={{ marginTop: 0 }}>Create Manual Skill</h3>
          <form className="grid" onSubmit={createSkill}>
            <div className="grid grid-2">
              <input
                placeholder="name"
                value={form.name}
                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                required
              />
              <input
                placeholder="display name"
                value={form.display_name}
                onChange={(e) => setForm((prev) => ({ ...prev, display_name: e.target.value }))}
              />
              <input
                placeholder="source"
                value={form.source}
                onChange={(e) => setForm((prev) => ({ ...prev, source: e.target.value }))}
              />
              <input
                placeholder="category"
                value={form.category}
                onChange={(e) => setForm((prev) => ({ ...prev, category: e.target.value }))}
                required
              />
            </div>
            <textarea
              placeholder="description"
              value={form.description}
              onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
            />
            <div className="grid grid-2">
              <select
                value={form.risk_level}
                onChange={(e) => setForm((prev) => ({ ...prev, risk_level: e.target.value as RiskLevel }))}
              >
                {riskOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <select
                value={form.status}
                onChange={(e) => setForm((prev) => ({ ...prev, status: e.target.value as ReviewStatus }))}
              >
                {statusOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <button type="submit">Create</button>
          </form>
        </article>
      </section>

      <article className="panel">
        <div className="stack-header">
          <div>
            <h3 style={{ margin: 0 }}>Security Overview</h3>
            <p className="small">Use these cards to inspect the current security distribution and focus the table.</p>
          </div>
          <span className="small">{visibleItems.length} visible / {items.length} loaded</span>
        </div>
        <div className="grid grid-2" style={{ marginTop: 14 }}>
          {[
            {
              key: "all" as SecurityFocus,
              title: "All Loaded",
              count: securitySummary.all,
              note: "Current backend filter result"
            },
            {
              key: "safe_to_use" as SecurityFocus,
              title: "Eligible",
              count: securitySummary.safe_to_use,
              note: "Default planning can use directly"
            },
            {
              key: "use_with_caution" as SecurityFocus,
              title: "Caution",
              count: securitySummary.use_with_caution,
              note: "Allowed but should be reviewed in context"
            },
            {
              key: "manual_review_required" as SecurityFocus,
              title: "Manual Review",
              count: securitySummary.manual_review_required,
              note: "Default planning de-prioritizes these"
            },
            {
              key: "block_or_quarantine" as SecurityFocus,
              title: "Excluded",
              count: securitySummary.block_or_quarantine,
              note: "Default planning excludes these"
            },
            {
              key: "operator_override" as SecurityFocus,
              title: "Overrides",
              count: securitySummary.operator_override,
              note: "Explicit operator security decision exists"
            }
          ].map((card) => {
            const active = securityFocus === card.key;
            return (
              <button
                key={card.key}
                type="button"
                className="card-button"
                onClick={() => setSecurityFocus(active ? "all" : card.key)}
                style={{
                  textAlign: "left",
                  borderColor: active ? "var(--accent)" : "var(--line)",
                  boxShadow: active ? "0 0 0 2px rgba(21, 94, 117, 0.15)" : "none"
                }}
              >
                <div className="small">{card.title}</div>
                <div style={{ fontSize: 28, fontWeight: 700, margin: "6px 0" }}>{card.count}</div>
                <div className="small">{card.note}</div>
              </button>
            );
          })}
        </div>
      </article>

      <article className="panel">
        <div className="stack-header">
          <div>
            <h3 style={{ margin: 0 }}>Tag And Security Curation</h3>
            <p className="small">
              Bind operator-managed tags, review skill safety posture, and keep operator decisions stable across future sync.
            </p>
          </div>
          <span className="small">{curatedSkill ? `editing #${curatedSkill.id}` : "no skill selected"}</span>
        </div>

        {curatedSkill ? (
          <div className="grid grid-2" style={{ marginTop: 14, alignItems: "start" }}>
            <div className="subpanel">
              <strong>{curatedSkill.display_name || curatedSkill.name}</strong>
              <div className="small">{curatedSkill.name}</div>
              <p className="small" style={{ fontSize: 13 }}>
                {curatedSkill.summary || curatedSkill.description}
              </p>
              <div className="chip-row">
                <span className="chip">{curatedSkill.category}</span>
                <span className="chip">{curatedSkill.source}</span>
                <span className="chip">{curatedSkill.status}</span>
              </div>
            </div>

            <div className="subpanel">
              <div className="stack-header">
                <strong>Operator Tags</strong>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => void saveOperatorTags()}
                  disabled={curationSaving}
                >
                  {curationSaving ? "Saving..." : "Save Operator Tags"}
                </button>
              </div>
              <textarea
                rows={4}
                value={operatorTagDraft}
                onChange={(e) => setOperatorTagDraft(e.target.value)}
                placeholder="desk:priority, domain:china_equity, strategy:short-term"
                style={{ marginTop: 10 }}
              />
              <p className="small">
                Comma-separated tag names. These are written as `operator` links and are preserved during sync.
              </p>
              <textarea
                rows={3}
                value={curationNote}
                onChange={(e) => setCurationNote(e.target.value)}
                placeholder="Approval note or change reason"
              />
              <div className="chip-row">
                {tagItems.slice(0, 18).map((tag) => (
                  <button
                    key={`quick-add-${tag.id}`}
                    type="button"
                    className="chip"
                    onClick={() => addOperatorTag(tag.name)}
                  >
                    + {tag.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="subpanel">
              <div className="stack-header">
                <strong>Security Review</strong>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {curatedSecurityReview ? <SecurityBadge tier={curatedSecurityReview.security_tier} /> : null}
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => curatedSkillId && void loadSecurityReview(curatedSkillId)}
                    disabled={securityLoading}
                  >
                    {securityLoading ? "Refreshing..." : "Refresh Review"}
                  </button>
                </div>
              </div>
              {curatedSecurityReview ? (
                <>
                  <div className="chip-row" style={{ marginTop: 10 }}>
                    <span className="chip">verdict {curatedSecurityReview.security_verdict}</span>
                    <span className="chip">score {curatedSecurityReview.security_score.toFixed(1)}</span>
                    {curatedSecurityReview.moderation_verdict ? (
                      <span className="chip">moderation {curatedSecurityReview.moderation_verdict}</span>
                    ) : null}
                  </div>
                  <div className="small" style={{ marginTop: 10 }}>
                    Permissions:{" "}
                    {Object.entries(curatedSecurityReview.permission_profile)
                      .filter(([, enabled]) => enabled)
                      .map(([key]) => key)
                      .join(" / ") || "none"}
                  </div>
                  {curatedSecurityReview.security_flags.length ? (
                    <ul className="plain-list small" style={{ marginTop: 10 }}>
                      {curatedSecurityReview.security_flags.map((flag) => (
                        <li key={flag}>{flag}</li>
                      ))}
                    </ul>
                  ) : null}
                  <label className="grid" style={{ gap: 6, marginTop: 10 }}>
                    <span className="small">Operator Decision</span>
                    <select
                      value={securityDecisionDraft}
                      onChange={(e) => setSecurityDecisionDraft(e.target.value)}
                    >
                      <option value="safe_to_use">safe_to_use</option>
                      <option value="use_with_caution">use_with_caution</option>
                      <option value="manual_review_required">manual_review_required</option>
                      <option value="block_or_quarantine">block_or_quarantine</option>
                    </select>
                  </label>
                  <textarea
                    rows={3}
                    value={securityNote}
                    onChange={(e) => setSecurityNote(e.target.value)}
                    placeholder="Security review note or override reason"
                    style={{ marginTop: 10 }}
                  />
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
                    <button type="button" onClick={() => void saveSecurityReview()} disabled={securitySaving}>
                      {securitySaving ? "Saving..." : "Save Security Decision"}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void clearSecurityOverride()}
                      disabled={securitySaving}
                    >
                      Clear Override
                    </button>
                  </div>
                  {curatedSecurityReview.operator_override ? (
                    <p className="small" style={{ marginTop: 10, marginBottom: 0 }}>
                      Current override: {curatedSecurityReview.operator_override.decision}
                      {curatedSecurityReview.operator_override.actor
                        ? ` by ${curatedSecurityReview.operator_override.actor}`
                        : ""}
                      {curatedSecurityReview.operator_override.updated_at
                        ? ` @ ${new Date(curatedSecurityReview.operator_override.updated_at).toLocaleString()}`
                        : ""}
                    </p>
                  ) : (
                    <p className="small" style={{ marginTop: 10, marginBottom: 0 }}>
                      No operator override recorded. Planner is using computed security posture only.
                    </p>
                  )}
                </>
              ) : (
                <p className="small" style={{ marginTop: 10, marginBottom: 0 }}>
                  No security review loaded yet.
                </p>
              )}
            </div>

            <div className="subpanel" style={{ gridColumn: "1 / -1" }}>
              <div className="stack-header">
                <strong>Current Linked Tags</strong>
                <span className="small">{curationLoading ? "loading..." : `${curatedSkillTags.length} links`}</span>
              </div>
              <div className="grid" style={{ marginTop: 10 }}>
                {curatedSkillTags.map((tag) => (
                  <div key={`${tag.id}-${tag.link_source}`} className="subpanel">
                    <div className="stack-header">
                      <div>
                        <strong>{tag.name}</strong>
                        <div className="small">
                          definition={tag.source} · link={tag.link_source} · confidence={tag.confidence}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void toggleTagDefinition(tag, curationNote)}
                      >
                        {tag.active ? "Deactivate Tag" : "Reactivate Tag"}
                      </button>
                    </div>
                    <p className="small" style={{ fontSize: 13 }}>
                      {tag.description}
                    </p>
                  </div>
                ))}
                {!curatedSkillTags.length && !curationLoading ? (
                  <div className="empty-state">
                    <p className="small">No tag links found for this skill.</p>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="subpanel" style={{ gridColumn: "1 / -1" }}>
              <div className="stack-header">
                <strong>Tag Change History</strong>
                <span className="small">{historyLoading ? "loading..." : `${curatedSkillHistory.length} entries`}</span>
              </div>
              <div className="grid grid-2" style={{ marginTop: 10 }}>
                <input
                  placeholder="filter by actor"
                  value={skillHistoryActorFilter}
                  onChange={(e) => setSkillHistoryActorFilter(e.target.value)}
                />
                <input
                  placeholder="filter by note"
                  value={skillHistoryNoteFilter}
                  onChange={(e) => setSkillHistoryNoteFilter(e.target.value)}
                />
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
                <button type="button" className="secondary" onClick={() => curatedSkillId && void loadSkillTagHistory(curatedSkillId)}>
                  Refresh History
                </button>
                {curatedSkillId ? (
                  <>
                    <a
                      className="chip"
                      href={`/api/backend/skills/${curatedSkillId}/tag-history/export?format=csv&${buildHistoryQuery(skillHistoryActorFilter, skillHistoryNoteFilter)}`}
                    >
                      Export CSV
                    </a>
                    <a
                      className="chip"
                      href={`/api/backend/skills/${curatedSkillId}/tag-history/export?format=jsonl&${buildHistoryQuery(skillHistoryActorFilter, skillHistoryNoteFilter)}`}
                    >
                      Export JSONL
                    </a>
                  </>
                ) : null}
              </div>
              <div className="grid" style={{ marginTop: 10 }}>
                {curatedSkillHistory.map((entry) => (
                  <div key={entry.id} className="subpanel">
                    <div className="stack-header">
                      <div>
                        <strong>{entry.action}</strong>
                        <div className="small">
                          {entry.actor} · {new Date(entry.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                    <p className="small" style={{ fontSize: 13 }}>
                      {entry.note || "No note provided."}
                    </p>
                    <div className="code">
                      {JSON.stringify(entry.before_state, null, 2)}
                      {"\n=>\n"}
                      {JSON.stringify(entry.after_state, null, 2)}
                    </div>
                  </div>
                ))}
                {!curatedSkillHistory.length && !historyLoading ? (
                  <div className="empty-state">
                    <p className="small">No tag change history recorded for this skill.</p>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="subpanel" style={{ gridColumn: "1 / -1" }}>
              <div className="stack-header">
                <strong>Security Review History</strong>
                <span className="small">{`${curatedSecurityHistory.length} entries`}</span>
              </div>
              <div className="grid grid-2" style={{ marginTop: 10 }}>
                <input
                  placeholder="filter by actor"
                  value={securityHistoryActorFilter}
                  onChange={(e) => setSecurityHistoryActorFilter(e.target.value)}
                />
                <input
                  placeholder="filter by note"
                  value={securityHistoryNoteFilter}
                  onChange={(e) => setSecurityHistoryNoteFilter(e.target.value)}
                />
              </div>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => curatedSkillId && void loadSecurityHistory(curatedSkillId)}
                    >
                      Refresh Security History
                    </button>
                    {curatedSkillId ? (
                      <>
                        <a
                          className="chip"
                          href={`/api/backend/skills/${curatedSkillId}/security-history/export?format=csv&${buildHistoryQuery(securityHistoryActorFilter, securityHistoryNoteFilter)}`}
                        >
                          Export CSV
                        </a>
                        <a
                          className="chip"
                          href={`/api/backend/skills/${curatedSkillId}/security-history/export?format=jsonl&${buildHistoryQuery(securityHistoryActorFilter, securityHistoryNoteFilter)}`}
                        >
                          Export JSONL
                        </a>
                      </>
                    ) : null}
                  </div>
              <div className="grid" style={{ marginTop: 10 }}>
                {curatedSecurityHistory.map((entry) => (
                  <div key={entry.id} className="subpanel">
                    <div className="stack-header">
                      <div>
                        <strong>{entry.action}</strong>
                        <div className="small">
                          {entry.actor} · {new Date(entry.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                    <p className="small" style={{ fontSize: 13 }}>
                      {entry.note || "No note provided."}
                    </p>
                    <div className="code">
                      {JSON.stringify(entry.before_state, null, 2)}
                      {"\n=>\n"}
                      {JSON.stringify(entry.after_state, null, 2)}
                    </div>
                  </div>
                ))}
                {!curatedSecurityHistory.length ? (
                  <div className="empty-state">
                    <p className="small">No security review history recorded for this skill.</p>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : (
          <div className="empty-state" style={{ marginTop: 14 }}>
            <p className="small">Choose “Curate / Review” on a skill below to open the operator review panel.</p>
          </div>
        )}
      </article>

      <section className="grid grid-2">
        <article className="panel">
          <div className="stack-header">
            <div>
              <h3 style={{ margin: 0 }}>Tag Library</h3>
              <p className="small">Use these tags as hard filters and toggle bad tag definitions off.</p>
            </div>
            <span className="small">{tagsLoading ? "loading..." : `${tagItems.length} tags`}</span>
          </div>
          <form className="grid" onSubmit={refreshTags}>
            <div className="grid grid-2">
              <input placeholder="search tags" value={tagQuery} onChange={(e) => setTagQuery(e.target.value)} />
              <input
                placeholder="category filter"
                value={tagCategory}
                onChange={(e) => setTagCategory(e.target.value)}
              />
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button type="submit" className="secondary">
                Refresh Tags
              </button>
            </div>
          </form>
          <div className="grid" style={{ marginTop: 14 }}>
            {tagItems.map((tag) => {
              const activeFilter = selectedTags.includes(tag.name);
              return (
                <div key={tag.id} className="subpanel">
                  <div className="stack-header">
                    <button
                      type="button"
                      className={`chip ${activeFilter ? "active-chip" : ""}`}
                      onClick={() => toggleTag(tag.name)}
                      title={tag.description}
                    >
                      {tag.name}
                    </button>
                    <button type="button" className="secondary" onClick={() => void toggleTagDefinition(tag)}>
                      {tag.active ? "Deactivate" : "Reactivate"}
                    </button>
                  </div>
                  <div className="small" style={{ marginTop: 8 }}>
                    {tag.category} · {tag.source} · usage {tag.usage_count}
                  </div>
                  <p className="small" style={{ fontSize: 13 }}>
                    {tag.description}
                  </p>
                </div>
              );
            })}
          </div>
        </article>

        <article className="panel">
          <div className="stack-header">
            <div>
              <h3 style={{ margin: 0 }}>Quick Search Diagnostics</h3>
              <p className="small">Inspect ranked search hits before they enter planning.</p>
            </div>
            <span className="small">{searchLoading ? "searching..." : `${searchResults.length} hits`}</span>
          </div>
          <form className="grid" onSubmit={submitSearch}>
            <input
              placeholder="A股 股票 分析 markdown"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button type="submit" disabled={searchLoading}>
                Run Ranked Search
              </button>
            </div>
          </form>

          <div className="grid" style={{ marginTop: 14 }}>
            {searchResults.map((result) => (
              <article key={result.skill.id} className="subpanel">
                <div className="stack-header">
                  <div>
                    <strong>{result.skill.display_name || result.skill.name}</strong>
                    <div className="small">
                      {result.skill.name} · {result.skill.source}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                    <QualityBadge tier={result.quality_tier} />
                    <SecurityBadge tier={result.security_tier} />
                  </div>
                </div>
                <p className="small" style={{ fontSize: 13 }}>
                  {result.skill.summary || result.skill.description}
                </p>
                <div className="chip-row">
                  <span className="chip">score {result.search_score.toFixed(1)}</span>
                  <span className="chip">quality {result.quality_score.toFixed(1)}</span>
                  <span className="chip">security {result.security_score.toFixed(1)}</span>
                  <span className="chip">{result.retrieval_source}</span>
                  {typeof result.official_score === "number" ? (
                    <span className="chip">official {result.official_score.toFixed(1)}</span>
                  ) : null}
                </div>
                {result.trust_signals.length ? (
                  <ul className="plain-list small">
                    {result.trust_signals.slice(0, 4).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}
                {result.security_flags.length ? (
                  <ul className="plain-list small">
                    {result.security_flags.slice(0, 4).map((item) => (
                      <li key={item}>安全审查: {item}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="small" style={{ marginTop: 8 }}>
                  {securityPlanningNote(result.security_verdict)}
                </div>
                {result.ranking_reasons.length ? (
                  <div className="code" style={{ marginTop: 10 }}>
                    {result.ranking_reasons.join("\n")}
                  </div>
                ) : null}
              </article>
            ))}
            {!searchResults.length && !searchLoading ? (
              <div className="empty-state">
                <p className="small">Run a ranked search to inspect why a skill is being preferred.</p>
              </div>
            ) : null}
          </div>
        </article>
      </section>

      <article className="panel">
        <div className="stack-header">
          <div>
            <h3 style={{ margin: 0 }}>Search Policy Rules</h3>
            <p className="small">
              Tune request-intent boosts and penalties without editing backend constants.
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <span className="small">{policyLoading ? "loading..." : `${policyItems.length} rules`}</span>
            <button type="button" className="secondary" onClick={() => void loadPolicies()}>
              Refresh Rules
            </button>
          </div>
        </div>
        <div className="grid" style={{ marginTop: 14 }}>
          {policyItems.map((rule) => {
            const draft = policyDrafts[rule.id] ?? {
              score_delta: String(rule.score_delta),
              priority: String(rule.priority),
              change_note: ""
            };
            return (
              <div key={rule.id} className="subpanel">
                <div className="stack-header">
                  <div>
                    <strong>{rule.name}</strong>
                    <div className="small">
                      intent={rule.intent_key} · active={rule.active ? "yes" : "no"}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void savePolicyRule(rule, !rule.active)}
                    disabled={policySavingId === rule.id}
                  >
                    {rule.active ? "Deactivate" : "Reactivate"}
                  </button>
                </div>
                <p className="small" style={{ fontSize: 13 }}>
                  {rule.description}
                </p>
                <div className="small">Reason: {rule.reason}</div>
                <div className="code" style={{ marginTop: 10 }}>
                  {JSON.stringify(rule.conditions, null, 2)}
                </div>
                <div className="grid grid-2" style={{ marginTop: 10 }}>
                  <label className="grid" style={{ gap: 6 }}>
                    <span className="small">Score Delta</span>
                    <input
                      type="number"
                      step="0.5"
                      value={draft.score_delta}
                      onChange={(e) =>
                        setPolicyDrafts((prev) => ({
                          ...prev,
                          [rule.id]: { ...draft, score_delta: e.target.value }
                        }))
                      }
                    />
                  </label>
                  <label className="grid" style={{ gap: 6 }}>
                    <span className="small">Priority</span>
                    <input
                      type="number"
                      step="1"
                      value={draft.priority}
                      onChange={(e) =>
                        setPolicyDrafts((prev) => ({
                          ...prev,
                          [rule.id]: { ...draft, priority: e.target.value }
                        }))
                      }
                    />
                  </label>
                </div>
                <div className="grid grid-2" style={{ marginTop: 10 }}>
                  <input
                    placeholder="history actor filter"
                    value={policyHistoryActorFilter}
                    onChange={(e) => setPolicyHistoryActorFilter(e.target.value)}
                  />
                  <input
                    placeholder="history note filter"
                    value={policyHistoryNoteFilter}
                    onChange={(e) => setPolicyHistoryNoteFilter(e.target.value)}
                  />
                </div>
                <textarea
                  rows={3}
                  value={draft.change_note}
                  onChange={(e) =>
                    setPolicyDrafts((prev) => ({
                      ...prev,
                      [rule.id]: { ...draft, change_note: e.target.value }
                    }))
                  }
                  placeholder="Change note or approval reason"
                  style={{ marginTop: 10 }}
                />
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void savePolicyRule(rule)}
                    disabled={policySavingId === rule.id}
                  >
                    {policySavingId === rule.id ? "Saving..." : "Save Rule"}
                  </button>
                  <button type="button" className="secondary" onClick={() => void loadPolicyHistory(rule.id)}>
                    Load History
                  </button>
                  <a
                    className="chip"
                    href={`/api/backend/skills/search/policies/${rule.id}/history/export?format=csv&${buildHistoryQuery(policyHistoryActorFilter, policyHistoryNoteFilter)}`}
                  >
                    Export CSV
                  </a>
                  <a
                    className="chip"
                    href={`/api/backend/skills/search/policies/${rule.id}/history/export?format=jsonl&${buildHistoryQuery(policyHistoryActorFilter, policyHistoryNoteFilter)}`}
                  >
                    Export JSONL
                  </a>
                </div>
                {policyHistory[rule.id]?.length ? (
                  <div className="grid" style={{ marginTop: 10 }}>
                    {policyHistory[rule.id].map((entry) => (
                      <div key={entry.id} className="subpanel">
                        <div className="stack-header">
                          <div>
                            <strong>{entry.action}</strong>
                            <div className="small">
                              {entry.actor} · {new Date(entry.created_at).toLocaleString()}
                            </div>
                          </div>
                        </div>
                        <p className="small" style={{ fontSize: 13 }}>
                          {entry.note || "No note provided."}
                        </p>
                        <div className="code">
                          {JSON.stringify(entry.before_state, null, 2)}
                          {"\n=>\n"}
                          {JSON.stringify(entry.after_state, null, 2)}
                        </div>
                        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => void rollbackPolicyRule(rule, entry.id)}
                            disabled={policySavingId === rule.id}
                          >
                            {policySavingId === rule.id ? "Saving..." : "Rollback To Before State"}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="small" style={{ marginTop: 10 }}>
                    No policy history loaded yet.
                  </div>
                )}
              </div>
            );
          })}
          {!policyItems.length && !policyLoading ? (
            <div className="empty-state">
              <p className="small">No search policy rules found.</p>
            </div>
          ) : null}
        </div>
      </article>

      <article className="panel">
        <div className="stack-header">
          <div>
            <h3 style={{ margin: 0 }}>Filtered Skill Catalog</h3>
            <p className="small">Shows synced and manual skills after tag and metadata filters.</p>
          </div>
          <span className="small">{loading ? "loading..." : `${items.length} rows`}</span>
        </div>

        <table>
          <thead>
            <tr>
              <th>Skill</th>
              <th>Catalog</th>
              <th>Signals</th>
              <th>Review</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.display_name || item.name}</strong>
                  <div className="small">{item.name}</div>
                  <div className="small">{item.summary || item.description}</div>
                </td>
                <td>
                  <div>{item.category}</div>
                  <div className="small">
                    {item.source}
                    {item.source_slug ? ` · ${item.source_slug}` : ""}
                  </div>
                  <div className="chip-row" style={{ marginTop: 8 }}>
                    {(item.tags || []).slice(0, 5).map((tag) => (
                      <span key={`${item.id}-${tag}`} className="chip">
                        {tag}
                      </span>
                    ))}
                  </div>
                </td>
                <td>
                  <div className="small">stars: {formatNumber(item.stats?.stars)}</div>
                  <div className="small">downloads: {formatNumber(item.stats?.downloads)}</div>
                  <div className="small">official: {item.is_official ? "yes" : "no"}</div>
                  <div className="small">
                    synced: {item.last_synced_at ? new Date(item.last_synced_at).toLocaleString() : "manual"}
                  </div>
                </td>
                <td>
                  <div>{item.risk_level}</div>
                  <div className="small">{item.status}</div>
                  <div className="chip-row" style={{ marginTop: 8 }}>
                    <SecurityBadge tier={item.security_tier} />
                    <span className="chip">security {Number(item.security_score || 0).toFixed(1)}</span>
                  </div>
                  {Array.isArray(item.security_flags) && item.security_flags.length > 0 ? (
                    <div className="small" style={{ marginTop: 8 }}>
                      {item.security_flags.slice(0, 2).join(" · ")}
                    </div>
                  ) : null}
                </td>
                <td style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button className="secondary" onClick={() => void loadSkillTagLinks(item.id)}>
                    Curate / Review
                  </button>
                  <button
                    className="secondary"
                    onClick={() =>
                      updateStatus(
                        item.id,
                        item.status === "approved" ? "pending" : "approved",
                        item.risk_level
                      )
                    }
                  >
                    Toggle Review
                  </button>
                  <button className="secondary" onClick={() => removeSkill(item.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {!visibleItems.length ? (
              <tr>
                <td colSpan={5}>
                  <div className="empty-state" style={{ minHeight: 120 }}>
                    <p className="small">
                      No skills match the current security focus.
                      {securityFocus !== "all" ? ` Focus: ${securityFocusLabel(securityFocus)}.` : ""}
                    </p>
                  </div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </article>
    </section>
  );
}
