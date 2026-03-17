"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { WorkflowGraph } from "./components/workflow-graph";
import type {
  CredentialKind,
  ExecutionMode,
  OutputFormat,
  RunRequestConfirmResponse,
  RunRequestPlanResponse,
  TargetType
} from "./lib/types";

type TargetDraft = {
  type: TargetType;
  label: string;
  value: string;
};

type CredentialDraft = {
  label: string;
  kind: CredentialKind;
  value: string;
};

const outputFormats: OutputFormat[] = ["json", "csv", "xlsx", "pdf", "markdown"];
const executionModes: ExecutionMode[] = ["remote", "local"];
const targetTypes: TargetType[] = ["url", "api", "text"];
const credentialKinds: CredentialKind[] = ["api_key", "token", "cookie", "basic_auth", "other"];

export default function HomePage() {
  const [goal, setGoal] = useState(
    "Fetch product data from this API, clean the records, and export a CSV I can review."
  );
  const [targets, setTargets] = useState<TargetDraft[]>([
    {
      type: "api",
      label: "Catalog endpoint",
      value: "https://example.com/api/products"
    }
  ]);
  const [credentials, setCredentials] = useState<CredentialDraft[]>([
    {
      label: "Partner token",
      kind: "token",
      value: ""
    }
  ]);
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("csv");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("remote");
  const [userNotes, setUserNotes] = useState("");
  const [result, setResult] = useState<RunRequestPlanResponse | null>(null);
  const [confirmation, setConfirmation] = useState<RunRequestConfirmResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const isActionablePlan = Boolean(result?.actionable && result.request && result.workflow_spec);

  function updateTarget(index: number, patch: Partial<TargetDraft>) {
    setTargets((prev) => prev.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function updateCredential(index: number, patch: Partial<CredentialDraft>) {
    setCredentials((prev) =>
      prev.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item))
    );
  }

  function addTarget() {
    setTargets((prev) => [...prev, { type: "url", label: "", value: "" }]);
  }

  function addCredential() {
    setCredentials((prev) => [...prev, { label: "", kind: "api_key", value: "" }]);
  }

  async function submitRequest(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    setConfirmation(null);

    try {
      const response = await fetch("/api/run-requests", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          goal,
          targets: targets.filter((item) => item.value.trim()),
          credentials: credentials
            .filter((item) => item.label.trim() && item.value.trim())
            .map((item) => ({
              ...item,
              ephemeral: true
            })),
          output_format: outputFormat,
          execution_mode: executionMode,
          user_notes: userNotes
        })
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(`Run request failed: ${body}`);
      }

      const data = (await response.json()) as RunRequestPlanResponse;
      setResult(data);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function confirmPlan() {
    if (!result?.request) {
      return;
    }
    setConfirming(true);
    setError("");

    try {
      const response = await fetch(`/api/run-requests/${result.request.id}/confirm`, {
        method: "POST"
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(`Confirm request failed: ${body}`);
      }

      const data = (await response.json()) as RunRequestConfirmResponse;
      setConfirmation(data);
    } catch (requestError) {
      setError((requestError as Error).message);
    } finally {
      setConfirming(false);
    }
  }

  return (
    <section className="grid" style={{ gap: 20 }}>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">One request, one plan, one result surface</p>
          <h2>Describe the task in plain language. ClawFlow prepares the execution plan.</h2>
          <p className="hero-text">
            This surface now behaves like a product intake, not an admin dashboard. Internal
            catalog curation stays in the console.
          </p>
          <div className="hero-actions">
            <Link href="/console">Open Internal Console</Link>
            <Link href="/workflows">Inspect Workflow Lab</Link>
          </div>
        </div>
        <div className="hero-card">
          <p className="eyebrow">Current MVP Scope</p>
          <ul className="plain-list">
            <li>Natural-language task intake</li>
            <li>Target and credential capture</li>
            <li>Planner-generated workflow preview</li>
            <li>Redacted request persistence for later execution</li>
          </ul>
        </div>
      </section>

      <section className="grid grid-2">
        <article className="panel">
          <h3 style={{ marginTop: 0 }}>Run Request</h3>
          <form className="grid" onSubmit={submitRequest} style={{ gap: 14 }}>
            <div>
              <label htmlFor="goal">Goal</label>
              <textarea
                id="goal"
                rows={5}
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                placeholder="Describe the automation outcome in plain language."
              />
            </div>

            <div className="grid" style={{ gap: 10 }}>
              <div className="stack-header">
                <h4 style={{ margin: 0 }}>Targets</h4>
                <button type="button" className="secondary" onClick={addTarget}>
                  Add Target
                </button>
              </div>
              {targets.map((target, index) => (
                <div key={`target-${index}`} className="subpanel grid" style={{ gap: 8 }}>
                  <div className="grid grid-2">
                    <select
                      value={target.type}
                      onChange={(event) => updateTarget(index, { type: event.target.value as TargetType })}
                    >
                      {targetTypes.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                    <input
                      value={target.label}
                      onChange={(event) => updateTarget(index, { label: event.target.value })}
                      placeholder="Label"
                    />
                  </div>
                  <input
                    value={target.value}
                    onChange={(event) => updateTarget(index, { value: event.target.value })}
                    placeholder="URL, API endpoint, or source text"
                  />
                </div>
              ))}
            </div>

            <div className="grid" style={{ gap: 10 }}>
              <div className="stack-header">
                <h4 style={{ margin: 0 }}>Credentials</h4>
                <button type="button" className="secondary" onClick={addCredential}>
                  Add Credential
                </button>
              </div>
              {credentials.map((credential, index) => (
                <div key={`credential-${index}`} className="subpanel grid" style={{ gap: 8 }}>
                  <div className="grid grid-2">
                    <input
                      value={credential.label}
                      onChange={(event) => updateCredential(index, { label: event.target.value })}
                      placeholder="Credential label"
                    />
                    <select
                      value={credential.kind}
                      onChange={(event) =>
                        updateCredential(index, { kind: event.target.value as CredentialKind })
                      }
                    >
                      {credentialKinds.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  </div>
                  <input
                    type="password"
                    value={credential.value}
                    onChange={(event) => updateCredential(index, { value: event.target.value })}
                    placeholder="Secret value"
                  />
                </div>
              ))}
            </div>

            <div className="grid grid-2">
              <select value={outputFormat} onChange={(event) => setOutputFormat(event.target.value as OutputFormat)}>
                {outputFormats.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <select
                value={executionMode}
                onChange={(event) => setExecutionMode(event.target.value as ExecutionMode)}
              >
                {executionModes.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>

            <textarea
              rows={3}
              value={userNotes}
              onChange={(event) => setUserNotes(event.target.value)}
              placeholder="Operator notes, delivery constraints, or guardrails"
            />

            <button type="submit" disabled={loading}>
              {loading ? "Generating plan..." : "Generate Execution Plan"}
            </button>
          </form>
          {error ? <p className="small">{error}</p> : null}
        </article>

        <article className="panel">
          <h3 style={{ marginTop: 0 }}>Planner Output</h3>
          {!result ? (
            <div className="empty-state">
              <p>The planner response will appear here after intake.</p>
              <p className="small">
                This preview is the bridge between user input and the future execution runtime.
              </p>
            </div>
          ) : (
            <div className="grid" style={{ gap: 14 }}>
              <div className="subpanel">
                <p className="eyebrow">
                  {isActionablePlan ? `Request #${result.request?.id}` : "Usage Guidance"}
                </p>
                <h4 style={{ margin: "4px 0 8px 0" }}>
                  {isActionablePlan ? result.workflow_spec?.name : "No workflow created yet"}
                </h4>
                <p className="small" style={{ margin: 0 }}>
                  {result.intake_summary.target_count} target(s) | {result.intake_summary.credential_count} credential
                  descriptor(s) | {result.intake_summary.execution_mode} mode | {result.intake_summary.output_format}
                </p>
              </div>

              <div className="subpanel">
                <p className="eyebrow">User Reply</p>
                <h4 style={{ margin: "4px 0 8px 0" }}>{result.assistant_response.headline}</h4>
                <p style={{ marginTop: 0 }}>{result.assistant_response.reply_text}</p>
                <p className="small" style={{ marginBottom: 0 }}>
                  {result.assistant_response.delivery_note}
                </p>
              </div>

              {isActionablePlan ? (
                <>
                  {result.workflow_summary ? (
                    <div className="subpanel">
                      <p className="eyebrow">Workflow Composition</p>
                      <h4 style={{ margin: "4px 0 8px 0" }}>{result.workflow_summary.headline}</h4>
                      <p style={{ marginTop: 0 }}>{result.workflow_summary.explanation}</p>
                      <p className="small" style={{ marginBottom: 12 }}>
                        Formula: {result.workflow_summary.formula}
                      </p>
                      <h5 style={{ marginBottom: 8 }}>Ordered Steps</h5>
                      <ul className="plain-list">
                        {result.workflow_summary.steps.map((item) => (
                          <li key={`${item.index}-${item.skill_ref}`}>
                            <strong>
                              {item.index}. {item.display_name}
                            </strong>{" "}
                            ({item.skill_ref})
                            <br />
                            {item.role}
                            <br />
                            {item.summary}
                            <br />
                            Planning: {item.planning_status}
                            {item.source_url ? (
                              <>
                                <br />
                                <a href={item.source_url} target="_blank" rel="noreferrer">
                                  Open Step Source
                                </a>
                              </>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                      <h5 style={{ marginBottom: 8 }}>Safety Guidance</h5>
                      <ul className="plain-list">
                        {result.workflow_summary.safety_guidance.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                      {result.workflow_summary.safety_review_items.length > 0 ? (
                        <>
                          <h5 style={{ marginBottom: 8 }}>Skills Requiring Attention</h5>
                          <ul className="plain-list">
                            {result.workflow_summary.safety_review_items.map((item) => (
                              <li key={`${item.skill_ref}-${item.display_name}`}>
                                <strong>{item.display_name}</strong> ({item.planning_status})
                                <br />
                                {item.note}
                                {item.security_flags.length > 0 ? (
                                  <>
                                    <br />
                                    {item.security_flags.join(" / ")}
                                  </>
                                ) : null}
                              </li>
                            ))}
                          </ul>
                        </>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="subpanel">
                    <div className="stack-header">
                      <h4 style={{ margin: 0 }}>Confirmation</h4>
                      <button type="button" onClick={confirmPlan} disabled={confirming}>
                        {confirming ? "Sending..." : "Confirm And Send Reply"}
                      </button>
                    </div>
                    <p style={{ marginTop: 12 }}>{result.assistant_response.confirmation_prompt}</p>
                    <p className="small" style={{ marginBottom: 0 }}>
                      Channel: {confirmation?.communication_preview.channel || result.communication_preview.channel} |
                      {" "}Status: {confirmation?.communication_preview.status || result.communication_preview.status}
                    </p>
                    <p style={{ marginBottom: 0 }}>
                      {confirmation?.communication_preview.body || result.communication_preview.body}
                    </p>
                  </div>

                  <WorkflowGraph
                    nodes={result.workflow_spec?.nodes || []}
                    edges={result.workflow_spec?.edges || []}
                  />
                </>
              ) : (
                <div className="subpanel">
                  <h4 style={{ marginTop: 0 }}>How To Use FlowHub</h4>
                  <p style={{ marginBottom: 0 }}>{result.communication_preview.body}</p>
                </div>
              )}

              <div className="subpanel">
                <h4 style={{ marginTop: 0 }}>Selected Skills</h4>
                <ul className="plain-list">
                  {result.selected_skills.length === 0 ? (
                    <li>
                      {isActionablePlan
                        ? "No indexed skill matched. The planner produced a generic fallback workflow."
                        : "This message did not reach workflow planning, so no skill was selected yet."}
                    </li>
                  ) : (
                    result.selected_skills.map((item) => (
                      <li key={item.skill_id}>
                        <strong>{item.display_name}</strong> ({item.category}) - {item.summary || item.description}
                        <br />
                        {item.selection_reason}
                        <br />
                        Quality: {item.quality_tier || "basic"} ({Number(item.quality_score || 0).toFixed(1)})
                        {Array.isArray(item.trust_signals) && item.trust_signals.length > 0
                          ? ` | ${item.trust_signals.join(" / ")}`
                          : ""}
                        <br />
                        Security: {item.security_tier || "caution"} ({Number(item.security_score || 0).toFixed(1)})
                        {Array.isArray(item.security_flags) && item.security_flags.length > 0
                          ? ` | ${item.security_flags.join(" / ")}`
                          : ""}
                        {item.security_verdict === "block_or_quarantine"
                          ? " | Default planning: excluded"
                          : item.security_verdict === "manual_review_required"
                            ? " | Default planning: manual review required"
                            : item.security_verdict === "use_with_caution"
                              ? " | Default planning: allowed with caution"
                              : " | Default planning: eligible"}
                        <br />
                        {item.usage_hint}
                        {item.source ? (
                          <>
                            <br />
                            Source: {item.source}
                            {item.source_slug ? ` / ${item.source_slug}` : ""}
                          </>
                        ) : null}
                        {item.source_url ? (
                          <>
                            <br />
                            <a href={item.source_url} target="_blank" rel="noreferrer">
                              Open Skill Detail
                            </a>
                          </>
                        ) : null}
                      </li>
                    ))
                  )}
                </ul>
              </div>

              {result.client_execution_guidance ? (
                <div className="subpanel">
                  <h4 style={{ marginTop: 0 }}>Client Execution</h4>
                  <p style={{ marginTop: 0 }}>{result.client_execution_guidance.summary}</p>
                  <p className="small">
                    Mode: {result.client_execution_guidance.mode} | AI runtime owner:{" "}
                    {result.client_execution_guidance.ai_runtime_owner}
                  </p>
                  <ul className="plain-list">
                    {result.client_execution_guidance.steps.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  {result.workflow_summary?.handoff_steps.length ? (
                    <>
                      <h5 style={{ marginBottom: 8 }}>Execution Handoff</h5>
                      <ul className="plain-list">
                        {result.workflow_summary.handoff_steps.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                  <h5 style={{ marginBottom: 8 }}>Fetch Targets</h5>
                  <ul className="plain-list">
                    {result.client_execution_guidance.skill_targets.map((item) => (
                      <li key={`${item.name}-${item.source_slug || item.source_url || item.display_name}`}>
                        <strong>{item.display_name}</strong> - {item.fetch_strategy}
                        <br />
                        {item.source}
                        {item.source_slug ? ` / ${item.source_slug}` : ""}
                        {item.source_url ? (
                          <>
                            <br />
                            <a href={item.source_url} target="_blank" rel="noreferrer">
                              Open Registry Source
                            </a>
                          </>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {result.client_install_guidance ? (
                <div className="subpanel">
                  <h4 style={{ marginTop: 0 }}>Client Install Guidance</h4>
                  <p style={{ marginTop: 0 }}>{result.client_install_guidance.summary}</p>
                  <p className="small">
                    Mode: {result.client_install_guidance.mode} | Status:{" "}
                    {result.client_install_guidance.status} | Requested:{" "}
                    {result.client_install_guidance.install_requested ? "yes" : "no"}
                  </p>
                  <ul className="plain-list">
                    {result.client_install_guidance.steps.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  {result.client_install_guidance.items.length > 0 ? (
                    <>
                      <h5 style={{ marginBottom: 8 }}>Install Targets</h5>
                      <ul className="plain-list">
                        {result.client_install_guidance.items.map((item) => (
                          <li
                            key={`${item.name}-${item.source_slug || item.source_url || item.display_name}`}
                          >
                            <strong>{item.display_name}</strong> - {item.fetch_strategy}
                            <br />
                            {item.source}
                            {item.source_slug ? ` / ${item.source_slug}` : ""}
                            {item.install_command ? (
                              <>
                                <br />
                                Install: <code>{item.install_command}</code>
                              </>
                            ) : null}
                            {item.install_command_windows ? (
                              <>
                                <br />
                                Windows: <code>{item.install_command_windows}</code>
                              </>
                            ) : null}
                            {item.source_url ? (
                              <>
                                <br />
                                <a href={item.source_url} target="_blank" rel="noreferrer">
                                  Open Install Source
                                </a>
                              </>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                  <p className="small" style={{ marginBottom: 0 }}>
                    {result.client_install_guidance.note}
                  </p>
                </div>
              ) : null}

              <div className="subpanel">
                <h4 style={{ marginTop: 0 }}>Usage</h4>
                <ul className="plain-list">
                  {result.assistant_response.usage_steps.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="subpanel">
                <h4 style={{ marginTop: 0 }}>Decision Log</h4>
                <ul className="plain-list">
                  {result.decision_log.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>

              {isActionablePlan ? (
                <div className="subpanel">
                  <h4 style={{ marginTop: 0 }}>Stored Credential Descriptors</h4>
                  <ul className="plain-list">
                    {result.request?.credential_descriptors.length === 0 ? (
                      <li>No credentials supplied.</li>
                    ) : (
                      result.request?.credential_descriptors.map((item) => (
                        <li key={`${item.label}-${item.preview}`}>
                          {item.label}: {item.preview}
                        </li>
                      ))
                    )}
                  </ul>
                </div>
              ) : null}

              <div className="subpanel">
                <h4 style={{ marginTop: 0 }}>Next Steps</h4>
                <ul className="plain-list">
                  {result.next_steps.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </article>
      </section>
    </section>
  );
}
