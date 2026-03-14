"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";

import { WorkflowGraph } from "../components/workflow-graph";
import { apiFetch } from "../lib/api";
import type {
  AuditAlertDelivery,
  ResolvedSkillRef,
  RunRequest,
  RunRequestConfirmResponse,
  RunRequestStatus,
  Skill,
  TelemetryAnomaly,
  TelemetryEvent
} from "../lib/types";

const statusOptions: Array<"" | RunRequestStatus> = ["", "planned", "queued", "running", "completed", "failed"];
type RunSecurityFocus =
  | "all"
  | "safe_to_use"
  | "use_with_caution"
  | "manual_review_required"
  | "block_or_quarantine"
  | "unresolved";
type RunNodePreset = "all" | "failed_only" | "failed_high_risk";

function parseRunStatus(value: string | null): "" | RunRequestStatus {
  return value === "planned" || value === "queued" || value === "running" || value === "completed" || value === "failed"
    ? value
    : "";
}

function parseRunSecurityFocus(value: string | null): RunSecurityFocus {
  return value === "safe_to_use" ||
    value === "use_with_caution" ||
    value === "manual_review_required" ||
    value === "block_or_quarantine" ||
    value === "unresolved"
    ? value
    : "all";
}

function parseRunNodePreset(value: string | null): RunNodePreset {
  return value === "failed_only" || value === "failed_high_risk" ? value : "all";
}

function parseRequestId(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function parseFlaggedOnly(value: string | null) {
  return value === "1" || value === "true";
}

function shortText(value: string, maxLength = 56) {
  const normalized = value.trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1)}...`;
}

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function statusTone(status: string) {
  if (status === "completed" || status === "success" || status === "ready_to_send") {
    return { background: "#d7ecef", color: "#155e75" };
  }
  if (status === "failed") {
    return { background: "#fbe3e6", color: "#9f1239" };
  }
  if (status === "queued" || status === "running") {
    return { background: "#efe6d4", color: "#8b5a2b" };
  }
  return { background: "#ece7db", color: "#4b5563" };
}

function buildSkillConsoleHref(skillRef: string | null | undefined) {
  if (!skillRef || skillRef === "output.export") {
    return null;
  }
  const params = new URLSearchParams({
    name: skillRef,
    security_focus: "all",
  });
  return `/skills?${params.toString()}`;
}

function securityTone(verdict: string | null | undefined) {
  if (verdict === "safe_to_use") {
    return { background: "#d7ecef", color: "#155e75" };
  }
  if (verdict === "use_with_caution") {
    return { background: "#efe6d4", color: "#8b5a2b" };
  }
  if (verdict === "block_or_quarantine") {
    return { background: "#fbe3e6", color: "#9f1239" };
  }
  if (verdict === "manual_review_required") {
    return { background: "#efe6d4", color: "#8b5a2b" };
  }
  return { background: "#ece7db", color: "#4b5563" };
}

function securityPlanningNote(skill: Skill | null | undefined) {
  if (!skill) {
    return "Default planning: unresolved";
  }
  if (skill.security_verdict === "block_or_quarantine") {
    return "Default planning: excluded";
  }
  if (skill.security_verdict === "manual_review_required") {
    return "Default planning: manual review required";
  }
  if (skill.security_verdict === "use_with_caution") {
    return "Default planning: allowed with caution";
  }
  return "Default planning: eligible";
}

function securityFocusTitle(focus: RunSecurityFocus) {
  switch (focus) {
    case "safe_to_use":
      return "Eligible";
    case "use_with_caution":
      return "Caution";
    case "manual_review_required":
      return "Manual Review";
    case "block_or_quarantine":
      return "Excluded";
    case "unresolved":
      return "Unresolved";
    default:
      return "All";
  }
}

function nodePresetTitle(preset: RunNodePreset) {
  switch (preset) {
    case "failed_only":
      return "Failed Only";
    case "failed_high_risk":
      return "Failed High Risk";
    default:
      return "All Nodes";
  }
}

function isHighRiskVerdict(verdict: string) {
  return verdict === "manual_review_required" || verdict === "block_or_quarantine";
}

function RunsPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [items, setItems] = useState<RunRequest[]>([]);
  const [telemetryItems, setTelemetryItems] = useState<TelemetryEvent[]>([]);
  const [alertDeliveries, setAlertDeliveries] = useState<AuditAlertDelivery[]>([]);
  const [resolvedSkillRefs, setResolvedSkillRefs] = useState<Record<string, ResolvedSkillRef>>({});
  const [anomalies, setAnomalies] = useState<TelemetryAnomaly[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<"" | RunRequestStatus>("");
  const [securityFocus, setSecurityFocus] = useState<RunSecurityFocus>("all");
  const [nodePreset, setNodePreset] = useState<RunNodePreset>("all");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [telemetryLoading, setTelemetryLoading] = useState(false);
  const [queryReady, setQueryReady] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState("");
  const [copySummaryFeedback, setCopySummaryFeedback] = useState("");
  const [copyPinnedFeedback, setCopyPinnedFeedback] = useState("");
  const [copyRequestSummaryFeedback, setCopyRequestSummaryFeedback] = useState("");
  const [replayingDeliveryId, setReplayingDeliveryId] = useState<number | null>(null);
  const [confirmResult, setConfirmResult] = useState<RunRequestConfirmResponse | null>(null);

  function resolvedSkillForRef(skillRef: string | null | undefined) {
    if (!skillRef) {
      return null;
    }
    return resolvedSkillRefs[skillRef]?.skill ?? null;
  }

  function securityVerdictForRef(skillRef: string | null | undefined) {
    if (!skillRef) {
      return "unresolved";
    }
    return resolvedSkillForRef(skillRef)?.security_verdict ?? "unresolved";
  }

  function matchesSecurityFocus(skillRef: string | null | undefined) {
    if (securityFocus === "all") {
      return true;
    }
    return securityVerdictForRef(skillRef) === securityFocus;
  }

  function matchesNodePreset(status: string, skillRef: string | null | undefined) {
    if (nodePreset === "all") {
      return true;
    }
    if (status !== "failed") {
      return false;
    }
    if (nodePreset === "failed_only") {
      return true;
    }
    return isHighRiskVerdict(securityVerdictForRef(skillRef));
  }

  async function loadRequests(nextStatus: "" | RunRequestStatus = statusFilter) {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: "40" });
      if (nextStatus) {
        params.set("status", nextStatus);
      }
      const data = await apiFetch<RunRequest[]>(`/run-requests/?${params.toString()}`);
      setItems(data);
      setSelectedRequestId((current) => {
        if (current && data.some((item) => item.id === current)) {
          return current;
        }
        return data[0]?.id ?? null;
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadTelemetry(workflowId: number | null) {
    if (!workflowId) {
      setTelemetryItems([]);
      return;
    }

    setTelemetryLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ workflow_id: String(workflowId), limit: "20" });
      const data = await apiFetch<TelemetryEvent[]>(`/telemetry/events?${params.toString()}`);
      setTelemetryItems(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setTelemetryLoading(false);
    }
  }

  async function loadAnomalies(workflowId: number | null) {
    if (!workflowId) {
      setAnomalies([]);
      return;
    }
    setError("");
    try {
      const params = new URLSearchParams({ workflow_id: String(workflowId), limit: "20" });
      const data = await apiFetch<TelemetryAnomaly[]>(`/telemetry/events/anomalies?${params.toString()}`);
      setAnomalies(data);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function loadAlertDeliveries(workflowId: number | null) {
    if (!workflowId) {
      setAlertDeliveries([]);
      return;
    }
    setError("");
    try {
      const params = new URLSearchParams({ workflow_id: String(workflowId), limit: "20" });
      const data = await apiFetch<AuditAlertDelivery[]>(`/telemetry/alerts?${params.toString()}`);
      setAlertDeliveries(data);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function loadResolvedSkills(runRequests: RunRequest[]) {
    const refs = Array.from(
      new Set(
        runRequests
          .flatMap((runRequest) => runRequest.workflow_spec.nodes ?? [])
          .map((node) => node.skill_ref)
          .filter((value): value is string => Boolean(value && value !== "output.export"))
      )
    );
    if (!refs.length) {
      setResolvedSkillRefs({});
      return;
    }

    setError("");
    try {
      const params = new URLSearchParams({ refs: refs.join(",") });
      const data = await apiFetch<ResolvedSkillRef[]>(`/skills/resolve?${params.toString()}`);
      const nextMap: Record<string, ResolvedSkillRef> = {};
      for (const item of data) {
        nextMap[item.requested_ref] = item;
      }
      setResolvedSkillRefs(nextMap);
    } catch (err) {
      setResolvedSkillRefs({});
      setError((err as Error).message);
    }
  }

  async function confirmSelectedRequest() {
    if (!selectedRequest || selectedRequest.status !== "planned") {
      return;
    }

    setConfirming(true);
    setError("");
    try {
      const data = await apiFetch<RunRequestConfirmResponse>(`/run-requests/${selectedRequest.id}/confirm`, {
        method: "POST"
      });
      setConfirmResult(data);
      await loadRequests(statusFilter);
      await loadTelemetry(data.workflow_spec.workflow_id ?? null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setConfirming(false);
    }
  }

  async function replayAlertDelivery(deliveryId: number) {
    setReplayingDeliveryId(deliveryId);
    setError("");
    try {
      await apiFetch<AuditAlertDelivery>(`/telemetry/alerts/${deliveryId}/replay`, {
        method: "POST"
      });
      await loadAlertDeliveries(selectedWorkflowId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setReplayingDeliveryId(null);
    }
  }

  async function copyCurrentView() {
    const query = searchParams.toString();
    const href = `${window.location.origin}${pathname}${query ? `?${query}` : ""}`;
    try {
      await navigator.clipboard.writeText(href);
      setCopyFeedback("Copied");
    } catch {
      setCopyFeedback("Copy failed");
    }
  }

  function buildRequestSummary(request: RunRequest) {
    const summary = [
      request.status,
      securityFocusTitle(securityFocus).toLowerCase(),
      nodePresetTitle(nodePreset).toLowerCase(),
      flaggedOnly ? "flagged only" : "all requests",
      `request #${request.id}`,
      request.workflow_spec.workflow_id ? `workflow #${request.workflow_spec.workflow_id}` : "workflow none",
      request.goal ? `goal ${shortText(request.goal)}` : "goal none",
      request.workflow_spec.name ? `workflow ${shortText(request.workflow_spec.name)}` : "workflow name none",
    ];
    if (request.id === selectedRequestId) {
      summary.push(`${filteredTelemetryItems.length} telemetry event(s)`);
      summary.push(`${filteredAnomalies.length} anomaly/anomalies`);
      if (alertDeliveries.length) {
        summary.push(`${alertDeliveries.length} alert delivery/deliveries`);
      }
    }
    return summary.join(" · ");
  }

  async function copyCurrentSummary() {
    const summary = [
      statusFilter || "all statuses",
      flaggedOnly ? "flagged only" : "all requests",
      `flagged ${flaggedRequestCount}`,
      selectedRequest ? buildRequestSummary(selectedRequest) : "request none · workflow none · goal none · workflow name none",
      `${filteredTelemetryItems.length} telemetry event(s)`,
      `${filteredAnomalies.length} anomaly/anomalies`,
    ].join(" · ");
    try {
      await navigator.clipboard.writeText(summary);
      setCopySummaryFeedback("Copied");
    } catch {
      setCopySummaryFeedback("Copy failed");
    }
  }

  async function copyRequestSummary(request: RunRequest) {
    try {
      await navigator.clipboard.writeText(buildRequestSummary(request));
      setCopyRequestSummaryFeedback(`Copied #${request.id}`);
    } catch {
      setCopyRequestSummaryFeedback(`Copy failed #${request.id}`);
    }
  }

  function buildPinnedRequestQuery(requestId: number | null = selectedRequestId) {
    const params = new URLSearchParams();
    if (securityFocus !== "all") {
      params.set("security_focus", securityFocus);
    }
    if (nodePreset !== "all") {
      params.set("node_preset", nodePreset);
    }
    if (flaggedOnly) {
      params.set("flagged_only", "1");
    }
    if (requestId) {
      params.set("request_id", String(requestId));
    }
    return params.toString();
  }

  function pinCurrentRequest(requestId: number | null = selectedRequestId) {
    if (!requestId) {
      return;
    }
    setSelectedRequestId(requestId);
    const nextQuery = buildPinnedRequestQuery(requestId);
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  }

  async function copyPinnedRequestView(requestId: number | null = selectedRequestId) {
    if (!requestId) {
      return;
    }
    const query = buildPinnedRequestQuery(requestId);
    const href = `${window.location.origin}${pathname}${query ? `?${query}` : ""}`;
    try {
      await navigator.clipboard.writeText(href);
      setCopyPinnedFeedback("Copied");
    } catch {
      setCopyPinnedFeedback("Copy failed");
    }
  }

  function applyRunPreset(preset: "all" | "flagged" | "flagged_failures") {
    setConfirmResult(null);
    setSelectedRequestId(null);
    setSecurityFocus("all");

    if (preset === "all") {
      setStatusFilter("");
      setNodePreset("all");
      setFlaggedOnly(false);
      return;
    }

    if (preset === "flagged") {
      setStatusFilter("");
      setNodePreset("all");
      setFlaggedOnly(true);
      return;
    }

    setStatusFilter("failed");
    setNodePreset("failed_high_risk");
    setFlaggedOnly(true);
  }

  function requestSecurityCounts(request: RunRequest) {
    return (request.workflow_spec.nodes ?? [])
      .filter((node) => node.skill_ref && node.skill_ref !== "output.export")
      .reduce<Record<RunSecurityFocus, number>>(
        (acc, node) => {
          const verdict = securityVerdictForRef(node.skill_ref) as RunSecurityFocus;
          acc[verdict] += 1;
          return acc;
        },
        {
          all: 0,
          safe_to_use: 0,
          use_with_caution: 0,
          manual_review_required: 0,
          block_or_quarantine: 0,
          unresolved: 0,
        }
      );
  }

  function requestSecurityBadge(request: RunRequest) {
    const counts = requestSecurityCounts(request);
    const total = Object.entries(counts)
      .filter(([key]) => key !== "all")
      .reduce((sum, [, value]) => sum + value, 0);
    if (!total) {
      return null;
    }
    if (counts.block_or_quarantine > 0) {
      return { verdict: "block_or_quarantine", label: `Excluded ${counts.block_or_quarantine}` };
    }
    if (counts.manual_review_required > 0) {
      return { verdict: "manual_review_required", label: `Manual Review ${counts.manual_review_required}` };
    }
    if (counts.use_with_caution > 0) {
      return { verdict: "use_with_caution", label: `Caution ${counts.use_with_caution}` };
    }
    if (counts.safe_to_use > 0) {
      return { verdict: "safe_to_use", label: `Eligible ${counts.safe_to_use}` };
    }
    return { verdict: "unresolved", label: "Security Pending" };
  }

  function requestIsFlagged(request: RunRequest) {
    const verdict = requestSecurityBadge(request)?.verdict;
    return Boolean(verdict && verdict !== "safe_to_use");
  }

  const filteredRequestItems = flaggedOnly ? items.filter((item) => requestIsFlagged(item)) : items;
  const flaggedRequestCount = items.filter((item) => requestIsFlagged(item)).length;
  const selectedRequest = filteredRequestItems.find((item) => item.id === selectedRequestId) ?? filteredRequestItems[0] ?? null;
  const selectedWorkflowId = selectedRequest?.workflow_spec.workflow_id ?? null;
  const workflowSkillMap = new Map(
    (selectedRequest?.workflow_spec.nodes ?? []).map((node) => [node.id, node.skill_ref ?? null])
  );

  useEffect(() => {
    setStatusFilter(parseRunStatus(searchParams.get("status")));
    setSecurityFocus(parseRunSecurityFocus(searchParams.get("security_focus")));
    setNodePreset(parseRunNodePreset(searchParams.get("node_preset")));
    setFlaggedOnly(parseFlaggedOnly(searchParams.get("flagged_only")));
    setSelectedRequestId(parseRequestId(searchParams.get("request_id")));
    setQueryReady(true);
  }, [searchParams]);

  useEffect(() => {
    if (!queryReady) {
      return;
    }
    void loadRequests(statusFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryReady, statusFilter]);

  useEffect(() => {
    if (!queryReady) {
      return;
    }
    if (!filteredRequestItems.length) {
      if (selectedRequestId !== null) {
        setSelectedRequestId(null);
      }
      return;
    }
    if (!selectedRequestId || !filteredRequestItems.some((item) => item.id === selectedRequestId)) {
      setSelectedRequestId(filteredRequestItems[0].id);
    }
  }, [queryReady, filteredRequestItems, selectedRequestId]);

  useEffect(() => {
    if (!queryReady) {
      return;
    }
    const params = new URLSearchParams();
    if (statusFilter) {
      params.set("status", statusFilter);
    }
    if (securityFocus !== "all") {
      params.set("security_focus", securityFocus);
    }
    if (nodePreset !== "all") {
      params.set("node_preset", nodePreset);
    }
    if (flaggedOnly) {
      params.set("flagged_only", "1");
    }
    if (selectedRequestId) {
      params.set("request_id", String(selectedRequestId));
    }
    const nextQuery = params.toString();
    const currentQuery = searchParams.toString();
    if (nextQuery === currentQuery) {
      return;
    }
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  }, [queryReady, pathname, router, searchParams, statusFilter, securityFocus, nodePreset, flaggedOnly, selectedRequestId]);

  useEffect(() => {
    void loadTelemetry(selectedWorkflowId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWorkflowId]);

  useEffect(() => {
    void loadAnomalies(selectedWorkflowId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWorkflowId]);

  useEffect(() => {
    void loadAlertDeliveries(selectedWorkflowId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWorkflowId]);

  useEffect(() => {
    void loadResolvedSkills(items);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const runExportBase = `/api/backend/run-requests/export?format=`;
  const runStatusParam = selectedRequest?.status ? `&status=${selectedRequest.status}` : statusFilter ? `&status=${statusFilter}` : "";
  const telemetryWorkflowParam = selectedWorkflowId ? `&workflow_id=${selectedWorkflowId}` : "";

  const statusCounts = items.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] ?? 0) + 1;
    return acc;
  }, {});
  const workflowNodes = selectedRequest?.workflow_spec.nodes ?? [];
  const workflowNodesWithSkills = workflowNodes.filter((node) => node.skill_ref && node.skill_ref !== "output.export");
  const workflowSecuritySummary = workflowNodesWithSkills.reduce<Record<RunSecurityFocus, number>>(
    (acc, node) => {
      const verdict = securityVerdictForRef(node.skill_ref) as RunSecurityFocus;
      acc.all += 1;
      acc[verdict] += 1;
      return acc;
    },
    {
      all: 0,
      safe_to_use: 0,
      use_with_caution: 0,
      manual_review_required: 0,
      block_or_quarantine: 0,
      unresolved: 0,
    }
  );
  const filteredWorkflowNodes = workflowNodesWithSkills.filter((node) => matchesSecurityFocus(node.skill_ref));
  const nodePresetSummary = telemetryItems.reduce<Record<RunNodePreset, number>>(
    (acc, event) => {
      for (const node of event.node_results) {
        const skillRef = workflowSkillMap.get(node.node_id);
        if (!matchesSecurityFocus(skillRef)) {
          continue;
        }
        acc.all += 1;
        if (node.status === "failed") {
          acc.failed_only += 1;
          if (isHighRiskVerdict(securityVerdictForRef(skillRef))) {
            acc.failed_high_risk += 1;
          }
        }
      }
      return acc;
    },
    {
      all: 0,
      failed_only: 0,
      failed_high_risk: 0,
    }
  );
  const filteredAnomalies = anomalies.filter((item) =>
    item.failed_node_ids.some((nodeId) => {
      const skillRef = workflowSkillMap.get(nodeId);
      return matchesSecurityFocus(skillRef) && matchesNodePreset("failed", skillRef);
    })
  );
  const filteredTelemetryItems = telemetryItems
    .map((event) => ({
      ...event,
      node_results: event.node_results.filter((node) => {
        const skillRef = workflowSkillMap.get(node.node_id);
        return matchesSecurityFocus(skillRef) && matchesNodePreset(node.status, skillRef);
      }),
    }))
    .filter((event) => event.node_results.length > 0);
  const currentViewSummary = [
    `status: ${statusFilter || "all"}`,
    `security: ${securityFocusTitle(securityFocus)}`,
    `preset: ${nodePresetTitle(nodePreset)}`,
    `requests: ${flaggedOnly ? "flagged only" : "all"}`,
    `flagged: ${flaggedRequestCount}`,
    selectedRequestId ? `request: #${selectedRequestId}` : "request: none",
    selectedWorkflowId ? `workflow: #${selectedWorkflowId}` : "workflow: none",
    selectedRequest?.goal ? `goal: ${shortText(selectedRequest.goal)}` : "goal: none",
    selectedRequest?.workflow_spec.name ? `workflow name: ${shortText(selectedRequest.workflow_spec.name)}` : "workflow name: none",
    `telemetry: ${filteredTelemetryItems.length} event(s)`,
    `anomalies: ${filteredAnomalies.length}`,
  ];
  const allRequestsPresetActive = !flaggedOnly && !statusFilter && nodePreset === "all" && securityFocus === "all";
  const flaggedRequestsPresetActive = flaggedOnly && !statusFilter && nodePreset === "all" && securityFocus === "all";
  const flaggedFailuresPresetActive =
    flaggedOnly && statusFilter === "failed" && nodePreset === "failed_high_risk" && securityFocus === "all";

  return (
    <section className="grid" style={{ gap: 18 }}>
      <article className="panel">
        <div className="stack-header">
          <div>
            <p className="eyebrow">Run Audit</p>
            <h2 style={{ margin: "6px 0 8px" }}>Inspect intake, confirm state, and client feedback</h2>
            <p className="small" style={{ fontSize: 14 }}>
              This page is for QA and deployment checks. It correlates run requests with workflow IDs
              and client telemetry.
            </p>
          </div>
          <div style={{ display: "grid", gap: 10, justifyItems: "end" }}>
            <div className="chip-row">
              {statusOptions
                .filter((item): item is RunRequestStatus => Boolean(item))
                .map((status) => (
                  <span key={status} className="chip">
                    {status}: {statusCounts[status] ?? 0}
                  </span>
                ))}
              <button
                type="button"
                className={`chip${flaggedOnly ? " active-chip" : ""}`}
                onClick={() => setFlaggedOnly((current) => !current)}
              >
                view: {flaggedOnly ? "flagged only" : "all requests"}
              </button>
              <button
                type="button"
                className={`chip${flaggedOnly ? " active-chip" : ""}`}
                onClick={() => setFlaggedOnly((current) => !current)}
                disabled={!flaggedOnly && flaggedRequestCount === 0}
              >
                flagged: {flaggedRequestCount}
              </button>
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <button type="button" className="secondary" onClick={() => void copyCurrentView()}>
                Copy Current View
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => pinCurrentRequest()}
                disabled={!selectedRequestId}
              >
                Pin Request
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => void copyPinnedRequestView()}
                disabled={!selectedRequestId}
              >
                Copy Pinned Request
              </button>
              <button type="button" className="secondary" onClick={() => void copyCurrentSummary()}>
                Copy Summary
              </button>
              {copyFeedback ? <span className="small">{copyFeedback}</span> : null}
              {copyPinnedFeedback ? <span className="small">{copyPinnedFeedback}</span> : null}
              {copySummaryFeedback ? <span className="small">{copySummaryFeedback}</span> : null}
              {copyRequestSummaryFeedback ? <span className="small">{copyRequestSummaryFeedback}</span> : null}
            </div>
            <div className="chip-row" style={{ justifyContent: "flex-end" }}>
              <button
                type="button"
                className={`chip${allRequestsPresetActive ? " active-chip" : ""}`}
                onClick={() => applyRunPreset("all")}
              >
                All Requests
              </button>
              <button
                type="button"
                className={`chip${flaggedRequestsPresetActive ? " active-chip" : ""}`}
                onClick={() => applyRunPreset("flagged")}
              >
                Flagged Requests
              </button>
              <button
                type="button"
                className={`chip${flaggedFailuresPresetActive ? " active-chip" : ""}`}
                onClick={() => applyRunPreset("flagged_failures")}
                disabled={!flaggedRequestCount}
              >
                Flagged Failures
              </button>
            </div>
          </div>
        </div>
        {error ? <p className="small" style={{ color: "#9f1239" }}>{error}</p> : null}
        <div className="subpanel" style={{ marginTop: 14 }}>
          <div className="stack-header">
            <strong>Current View</strong>
            <span className="small">Shareable audit summary</span>
          </div>
          <p className="small" style={{ marginTop: 10 }}>
            `Pin Request` drops the status filter and keeps the current request, security focus, and node preset.
          </p>
          <div className="chip-row" style={{ marginTop: 10 }}>
            {currentViewSummary.map((item) => (
              <span key={item} className="chip">
                {item}
              </span>
            ))}
          </div>
        </div>
      </article>

      <section className="grid grid-2" style={{ alignItems: "start" }}>
        <article className="panel">
          <div className="stack-header">
            <h3 style={{ margin: 0 }}>Run Requests</h3>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <select
                value={statusFilter}
                onChange={(event) => {
                  const nextValue = event.target.value as "" | RunRequestStatus;
                  setStatusFilter(nextValue);
                }}
              >
                <option value="">all statuses</option>
                {statusOptions
                  .filter((item): item is RunRequestStatus => Boolean(item))
                  .map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
              </select>
              <button type="button" className="secondary" onClick={() => void loadRequests(statusFilter)}>
                {loading ? "Refreshing..." : "Refresh"}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setFlaggedOnly((current) => !current)}
              >
                {flaggedOnly ? "Show All Requests" : `Only Flagged Requests (${flaggedRequestCount})`}
              </button>
              <a className="chip" href={`${runExportBase}csv${runStatusParam}`}>
                Export CSV
              </a>
              <a className="chip" href={`${runExportBase}jsonl${runStatusParam}`}>
                Export JSONL
              </a>
            </div>
          </div>

          <div className="grid" style={{ marginTop: 14 }}>
            {filteredRequestItems.map((item) => {
              const tone = statusTone(item.status);
              const active = item.id === selectedRequest?.id;
              const requestSecurity = requestSecurityBadge(item);
              const requestSecurityStyle = requestSecurity ? securityTone(requestSecurity.verdict) : null;
              const requestSummaryPreview = shortText(buildRequestSummary(item), active ? 180 : 120);
              return (
                <div
                  key={item.id}
                  className="subpanel"
                  style={{
                    borderColor: active
                      ? "#155e75"
                      : requestSecurity?.verdict === "block_or_quarantine"
                        ? "#9f1239"
                        : requestSecurity?.verdict === "manual_review_required"
                          ? "#8b5a2b"
                          : undefined,
                    background: active
                      ? "rgba(215, 236, 239, 0.42)"
                      : requestSecurity?.verdict === "block_or_quarantine"
                        ? "rgba(251, 227, 230, 0.42)"
                        : requestSecurity?.verdict === "manual_review_required"
                          ? "rgba(239, 230, 212, 0.42)"
                          : undefined
                  }}
                >
                  <button
                    type="button"
                    className="card-button"
                    style={{ textAlign: "left", width: "100%", background: "transparent", border: "none", padding: 0 }}
                    onClick={() => {
                      setConfirmResult(null);
                      setSelectedRequestId(item.id);
                    }}
                  >
                    <div className="stack-header">
                      <strong>#{item.id}</strong>
                      <div className="chip-row" style={{ justifyContent: "flex-end" }}>
                        <span
                          className="chip"
                          style={{ background: tone.background, color: tone.color, borderColor: tone.background }}
                        >
                          {item.status}
                        </span>
                        {requestSecurity ? (
                          <span
                            className="chip"
                            style={{
                              background: requestSecurityStyle?.background,
                              color: requestSecurityStyle?.color,
                              borderColor: requestSecurityStyle?.background
                            }}
                          >
                            {requestSecurity.label}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <div style={{ marginTop: 8, fontWeight: 600 }}>{item.goal}</div>
                    <div className="small" style={{ marginTop: 6 }}>
                      workflow {item.workflow_spec.workflow_id ?? "n/a"} · {new Date(item.created_at).toLocaleString()}
                    </div>
                    <div className="small" style={{ marginTop: 8 }}>
                      {requestSummaryPreview}
                    </div>
                  </button>
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => pinCurrentRequest(item.id)}
                    >
                      Pin
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void copyPinnedRequestView(item.id)}
                    >
                      Copy Pinned
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void copyRequestSummary(item)}
                    >
                      Copy Summary
                    </button>
                  </div>
                </div>
              );
            })}

            {!filteredRequestItems.length && !loading ? (
              <div className="empty-state">
                <p className="small">
                  {flaggedOnly ? "No flagged run requests match the current filter." : "No run requests match the current filter."}
                </p>
              </div>
            ) : null}
          </div>
        </article>

        <article className="panel">
          <div className="stack-header">
            <div>
              <h3 style={{ margin: 0 }}>Request Detail</h3>
              <p className="small">
                Review targets, masked credentials, planning notes, and current workflow shape.
              </p>
            </div>
            {selectedRequest?.status === "planned" ? (
              <button type="button" onClick={() => void confirmSelectedRequest()} disabled={confirming}>
                {confirming ? "Confirming..." : "Confirm Selected"}
              </button>
            ) : null}
          </div>

          {selectedRequest ? (
            <div className="grid" style={{ marginTop: 14 }}>
              <div className="subpanel">
                <div className="stack-header">
                  <strong>{selectedRequest.goal}</strong>
                  <span className="small">workflow {selectedRequest.workflow_spec.workflow_id ?? "n/a"}</span>
                </div>
                {selectedRequest.user_notes ? (
                  <p className="small" style={{ fontSize: 13 }}>{selectedRequest.user_notes}</p>
                ) : null}
                <div className="chip-row">
                  <span className="chip">{selectedRequest.output_format}</span>
                  <span className="chip">{selectedRequest.execution_mode}</span>
                  <span className="chip">{selectedRequest.targets.length} target(s)</span>
                  <span className="chip">{selectedRequest.credential_descriptors.length} credential(s)</span>
                </div>
              </div>

              <div className="subpanel">
                <strong>Targets</strong>
                <pre className="code">{formatJson(selectedRequest.targets)}</pre>
              </div>

              <div className="subpanel">
                <strong>Credential Descriptors</strong>
                <pre className="code">{formatJson(selectedRequest.credential_descriptors)}</pre>
              </div>

              <div className="subpanel">
                <strong>Planning Notes</strong>
                <ul className="plain-list small">
                  {selectedRequest.planning_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>

              <div className="subpanel">
                <strong>Workflow Graph</strong>
                <div style={{ marginTop: 10 }}>
                  <WorkflowGraph
                    nodes={selectedRequest.workflow_spec.nodes}
                    edges={selectedRequest.workflow_spec.edges}
                  />
                </div>
              </div>

              <div className="subpanel">
                <strong>Workflow Skills</strong>
                <div className="grid" style={{ marginTop: 10 }}>
                  {filteredWorkflowNodes.map((node) => {
                      const href = buildSkillConsoleHref(node.skill_ref);
                      const resolvedSkill = resolvedSkillForRef(node.skill_ref);
                      const verdictTone = securityTone(resolvedSkill?.security_verdict);
                      return (
                        <div key={node.id} className="subpanel">
                          <div className="stack-header">
                            <strong>{node.name}</strong>
                            <span className="small">{node.id}</span>
                          </div>
                          <div className="small" style={{ marginTop: 8 }}>
                            {node.skill_ref}
                          </div>
                          <div className="chip-row" style={{ marginTop: 8 }}>
                            <span
                              className="chip"
                              style={{
                                background: verdictTone.background,
                                color: verdictTone.color,
                                borderColor: verdictTone.background
                              }}
                            >
                              {resolvedSkill?.security_verdict ?? "unresolved"}
                            </span>
                            {resolvedSkill?.security_tier ? (
                              <span className="chip">tier {resolvedSkill.security_tier}</span>
                            ) : null}
                          </div>
                          <div className="small" style={{ marginTop: 8 }}>
                            {securityPlanningNote(resolvedSkill)}
                          </div>
                          {href ? (
                            <div style={{ marginTop: 10 }}>
                              <Link className="chip" href={href}>
                                Review Skill Security
                              </Link>
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  {!filteredWorkflowNodes.length ? (
                    <div className="empty-state">
                      <p className="small">
                        No workflow skills match the current security focus: {securityFocusTitle(securityFocus)}.
                      </p>
                    </div>
                  ) : null}
                </div>
              </div>

              {confirmResult ? (
                <div className="subpanel">
                  <strong>Latest Confirm Response</strong>
                  <p className="small" style={{ fontSize: 13 }}>{confirmResult.assistant_response.reply_text}</p>
                  <pre className="code">{formatJson(confirmResult.communication_preview)}</pre>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="empty-state" style={{ marginTop: 14 }}>
              <p className="small">Select a run request to inspect its current state.</p>
            </div>
          )}
        </article>
      </section>

      <article className="panel">
        <div className="stack-header">
          <div>
            <h3 style={{ margin: 0 }}>Client Telemetry</h3>
            <p className="small">
              Filtered automatically by the selected request&apos;s workflow ID.
            </p>
          </div>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              void loadTelemetry(selectedWorkflowId);
              void loadAnomalies(selectedWorkflowId);
              void loadAlertDeliveries(selectedWorkflowId);
            }}
          >
            {telemetryLoading ? "Refreshing..." : "Refresh Telemetry"}
          </button>
        </div>

        <div className="grid grid-3" style={{ marginTop: 14 }}>
          {[
            { key: "all" as RunSecurityFocus, note: "All workflow skills in this request" },
            { key: "safe_to_use" as RunSecurityFocus, note: "Default planning can use directly" },
            { key: "use_with_caution" as RunSecurityFocus, note: "Allowed with extra care" },
            { key: "manual_review_required" as RunSecurityFocus, note: "Needs human review before trust" },
            { key: "block_or_quarantine" as RunSecurityFocus, note: "Excluded from default planning" },
            { key: "unresolved" as RunSecurityFocus, note: "No matching catalog skill was resolved" },
          ].map((card) => {
            const active = securityFocus === card.key;
            return (
              <button
                key={card.key}
                type="button"
                className="panel card-button"
                style={{
                  textAlign: "left",
                  borderColor: active ? "#155e75" : undefined,
                  background: active ? "rgba(215, 236, 239, 0.42)" : undefined
                }}
                onClick={() => setSecurityFocus(card.key)}
              >
                <div className="small">{securityFocusTitle(card.key)}</div>
                <div style={{ fontSize: 28, fontWeight: 700, margin: "6px 0" }}>
                  {workflowSecuritySummary[card.key]}
                </div>
                <div className="small">{card.note}</div>
              </button>
            );
          })}
        </div>

        <div className="grid grid-3" style={{ marginTop: 14 }}>
          {[
            { key: "all" as RunNodePreset, note: "Every telemetry node that matches the current security focus" },
            { key: "failed_only" as RunNodePreset, note: "Only failed nodes, regardless of verdict" },
            { key: "failed_high_risk" as RunNodePreset, note: "Only failed nodes with manual review or excluded verdicts" },
          ].map((card) => {
            const active = nodePreset === card.key;
            return (
              <button
                key={card.key}
                type="button"
                className="panel card-button"
                style={{
                  textAlign: "left",
                  borderColor: active ? "#9f1239" : undefined,
                  background: active ? "rgba(251, 227, 230, 0.42)" : undefined
                }}
                onClick={() => setNodePreset(card.key)}
              >
                <div className="small">{nodePresetTitle(card.key)}</div>
                <div style={{ fontSize: 28, fontWeight: 700, margin: "6px 0" }}>
                  {nodePresetSummary[card.key]}
                </div>
                <div className="small">{card.note}</div>
              </button>
            );
          })}
        </div>

        <div className="chip-row" style={{ marginTop: 12 }}>
          <a className="chip" href={`/api/backend/telemetry/events/export?format=csv&failed_only=true${telemetryWorkflowParam}`}>
            Failed CSV
          </a>
          <a className="chip" href={`/api/backend/telemetry/events/export?format=jsonl&failed_only=true${telemetryWorkflowParam}`}>
            Failed JSONL
          </a>
          <a className="chip" href={`/api/backend/telemetry/alerts/export?format=csv${telemetryWorkflowParam}`}>
            Alert CSV
          </a>
          <a className="chip" href={`/api/backend/telemetry/alerts/export?format=jsonl${telemetryWorkflowParam}`}>
            Alert JSONL
          </a>
        </div>

        <div className="grid" style={{ marginTop: 14 }}>
          {alertDeliveries.length ? (
            <article className="subpanel">
              <div className="stack-header">
                <strong>Webhook Alert Deliveries</strong>
                <span className="small">{alertDeliveries.length}</span>
              </div>
              <div className="grid" style={{ marginTop: 10 }}>
                {alertDeliveries.map((item) => {
                  const tone = statusTone(item.status === "delivered" ? "completed" : "failed");
                  const severity =
                    item.payload && typeof item.payload === "object" && typeof item.payload.severity === "string"
                      ? item.payload.severity
                      : null;
                  const routeMeta =
                    item.payload && typeof item.payload === "object" && item.payload.alert_route && typeof item.payload.alert_route === "object"
                      ? (item.payload.alert_route as { destination_name?: string; matched_rules?: string[] })
                      : null;
                  return (
                    <div key={item.id} className="subpanel">
                      <div className="stack-header">
                        <div>
                          <strong>{item.run_id}</strong>
                          <div className="small">delivery #{item.id}</div>
                        </div>
                        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                          <span
                            className="chip"
                            style={{ background: tone.background, color: tone.color, borderColor: tone.background }}
                          >
                            {item.status}
                          </span>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => void replayAlertDelivery(item.id)}
                            disabled={replayingDeliveryId === item.id}
                          >
                            {replayingDeliveryId === item.id ? "Replaying..." : "Replay"}
                          </button>
                        </div>
                      </div>
                      <div className="small">
                        attempts {item.attempt_count} · code {item.response_status_code ?? "n/a"}
                      </div>
                      {severity ? <div className="small">severity {severity}</div> : null}
                      <div className="small">
                        {item.destination}
                      </div>
                      {routeMeta ? (
                        <div className="small">
                          route {routeMeta.destination_name || "n/a"}
                          {Array.isArray(routeMeta.matched_rules) && routeMeta.matched_rules.length
                            ? ` · rules ${routeMeta.matched_rules.join(", ")}`
                            : ""}
                        </div>
                      ) : null}
                      <div className="small">
                        created {new Date(item.created_at).toLocaleString()}
                        {item.delivered_at ? ` · delivered ${new Date(item.delivered_at).toLocaleString()}` : ""}
                      </div>
                      {item.error_message ? (
                        <p className="small" style={{ color: "#9f1239" }}>{item.error_message}</p>
                      ) : null}
                      {item.response_body_preview ? (
                        <pre className="code">{item.response_body_preview}</pre>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </article>
          ) : null}

          {filteredAnomalies.length ? (
            <article className="subpanel">
              <div className="stack-header">
                <strong>Detected Anomalies</strong>
                <span className="small">{filteredAnomalies.length}</span>
              </div>
              <div className="grid" style={{ marginTop: 10 }}>
                {filteredAnomalies.map((item) => {
                  const visibleFailedNodeIds = item.failed_node_ids.filter((nodeId) => {
                    const skillRef = workflowSkillMap.get(nodeId);
                    return matchesSecurityFocus(skillRef) && matchesNodePreset("failed", skillRef);
                  });
                  return (
                    <div key={`${item.event_id}-${item.run_id}`} className="subpanel">
                      <div className="stack-header">
                        <strong>{item.run_id}</strong>
                        <span className="chip" style={{ background: "#fbe3e6", color: "#9f1239", borderColor: "#fbe3e6" }}>
                          failed nodes {visibleFailedNodeIds.length}
                        </span>
                      </div>
                      <div className="small">
                        workflow {item.workflow_id ?? "n/a"} · {new Date(item.created_at).toLocaleString()}
                      </div>
                      <div className="chip-row" style={{ marginTop: 8 }}>
                        {visibleFailedNodeIds.map((nodeId) => {
                          const skillRef = workflowSkillMap.get(nodeId);
                          const resolvedSkill = resolvedSkillForRef(skillRef);
                          return (
                            <span key={`${item.event_id}-${nodeId}`} className="chip">
                              {nodeId}
                              {skillRef ? ` → ${skillRef}` : ""}
                              {resolvedSkill?.security_verdict ? ` · ${resolvedSkill.security_verdict}` : ""}
                            </span>
                          );
                        })}
                      </div>
                      <div className="chip-row" style={{ marginTop: 8 }}>
                        {visibleFailedNodeIds.map((nodeId) => {
                          const skillRef = workflowSkillMap.get(nodeId);
                          const href = buildSkillConsoleHref(skillRef);
                          return href ? (
                            <Link key={`${item.event_id}-${nodeId}-link`} className="chip" href={href}>
                              Review {skillRef}
                            </Link>
                          ) : null;
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </article>
          ) : null}

          {filteredTelemetryItems.map((event) => (
            <article key={event.id} className="subpanel">
              <div className="stack-header">
                <div>
                  <strong>{event.run_id}</strong>
                  <div className="small">
                    workflow {event.workflow_id ?? "n/a"} · {new Date(event.created_at).toLocaleString()}
                  </div>
                </div>
                <span className="chip">
                  nodes {event.node_results.length}
                </span>
              </div>
              <pre className="code" style={{ marginTop: 10 }}>{formatJson(event.summary)}</pre>
              <div className="grid" style={{ marginTop: 10 }}>
                {event.node_results.map((node) => {
                  const tone = statusTone(node.status);
                  const skillRef = workflowSkillMap.get(node.node_id);
                  const href = buildSkillConsoleHref(skillRef);
                  const resolvedSkill = resolvedSkillForRef(skillRef);
                  const verdictTone = securityTone(resolvedSkill?.security_verdict);
                  return (
                    <div key={`${event.id}-${node.node_id}`} className="subpanel">
                      <div className="stack-header">
                        <div>
                          <strong>{node.node_id}</strong>
                          {skillRef ? <div className="small">{skillRef}</div> : null}
                        </div>
                        <div className="chip-row">
                          <span
                            className="chip"
                            style={{ background: tone.background, color: tone.color, borderColor: tone.background }}
                          >
                            {node.status}
                          </span>
                          {resolvedSkill ? (
                            <span
                              className="chip"
                              style={{
                                background: verdictTone.background,
                                color: verdictTone.color,
                                borderColor: verdictTone.background
                              }}
                            >
                              {resolvedSkill.security_verdict}
                            </span>
                          ) : null}
                        </div>
                      </div>
                      {resolvedSkill ? (
                        <div className="small" style={{ marginBottom: 8 }}>
                          {securityPlanningNote(resolvedSkill)}
                        </div>
                      ) : null}
                      {node.error ? <p className="small" style={{ color: "#9f1239" }}>{node.error}</p> : null}
                      {href ? (
                        <div style={{ marginBottom: 10 }}>
                          <Link className="chip" href={href}>
                            Review Skill Security
                          </Link>
                        </div>
                      ) : null}
                      <pre className="code">{formatJson(node.output)}</pre>
                    </div>
                  );
                })}
              </div>
            </article>
          ))}

          {!filteredTelemetryItems.length && !telemetryLoading ? (
            <div className="empty-state">
              <p className="small">
                {telemetryItems.length
                  ? `No telemetry nodes match the current view: ${securityFocusTitle(securityFocus)} + ${nodePresetTitle(nodePreset)}.`
                  : "No telemetry events found for the selected workflow. This usually means the client has not executed or reported back yet."}
              </p>
            </div>
          ) : null}
        </div>
      </article>
    </section>
  );
}

export default function RunsPage() {
  return (
    <Suspense fallback={<section className="grid"><article className="panel"><p className="small">Loading run audit...</p></article></section>}>
      <RunsPageContent />
    </Suspense>
  );
}
