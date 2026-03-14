import Link from "next/link";

export default function ConsolePage() {
  return (
    <section className="grid" style={{ gap: 20 }}>
      <article className="panel">
        <p className="eyebrow">Internal Console</p>
        <h2 style={{ marginTop: 0 }}>Operate the catalog and planning baseline</h2>
        <p className="small" style={{ fontSize: 14 }}>
          These pages are for curation and QA. End users should stay on the run request
          intake page.
        </p>
      </article>

      <section className="grid grid-2">
        <article className="panel">
          <h3>Skill Management</h3>
          <p>Review imported skills, risk levels, security posture, and publication status.</p>
          <Link href="/skills">Open Skills</Link>
        </article>
        <article className="panel">
          <h3>Security Triage</h3>
          <p>Jump directly into blocked or manually reviewed skills that may affect default planning.</p>
          <Link href="/skills?security_focus=block_or_quarantine">Open Excluded Skills</Link>
        </article>
        <article className="panel">
          <h3>Recipe Management</h3>
          <p>Maintain scenario templates used as planner hints and fallback recipes.</p>
          <Link href="/recipes">Open Recipes</Link>
        </article>
        <article className="panel">
          <h3>Workflow Management</h3>
          <p>Inspect generated workflow specs and validate node and edge structure.</p>
          <Link href="/workflows">Open Workflows</Link>
        </article>
        <article className="panel">
          <h3>Run Audit</h3>
          <p>Trace run requests, confirmation state, and client telemetry in one QA surface.</p>
          <div style={{ display: "grid", gap: 8 }}>
            <Link href="/runs">Open Run Audit</Link>
            <Link href="/runs?flagged_only=1">Open Flagged Requests</Link>
            <Link href="/runs?status=failed&flagged_only=1&node_preset=failed_high_risk">Open Flagged Failures</Link>
            <Link href="/runs?status=failed&node_preset=failed_only">Open Failed Runs</Link>
            <Link href="/runs?status=failed&security_focus=block_or_quarantine&node_preset=failed_high_risk">
              Open Excluded Failed Runs
            </Link>
          </div>
        </article>
        <article className="panel">
          <h3>Operations</h3>
          <p>Search and export operator tag changes, policy edits, and rollback history.</p>
          <Link href="/operations">Open Operations</Link>
        </article>
        <article className="panel">
          <h3>User Entry</h3>
          <p>Return to the public intake surface that captures natural-language tasks.</p>
          <Link href="/">Open Run Intake</Link>
        </article>
      </section>
    </section>
  );
}
