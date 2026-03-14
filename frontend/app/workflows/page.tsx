"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import { PlannedWorkflow, ReviewStatus, RiskLevel, Workflow } from "../lib/types";
import { WorkflowGraph } from "../components/workflow-graph";

const statusOptions: ReviewStatus[] = ["draft", "pending", "approved", "rejected", "archived"];
const riskOptions: RiskLevel[] = ["low", "medium", "high"];

export default function WorkflowsPage() {
  const [items, setItems] = useState<Workflow[]>([]);
  const [error, setError] = useState("");
  const [planInput, setPlanInput] = useState("analyze monthly incident report");
  const [planned, setPlanned] = useState<PlannedWorkflow | null>(null);

  async function load() {
    setError("");
    try {
      const data = await apiFetch<Workflow[]>("/workflows/");
      setItems(data);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function createFromPlanner(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const plan = await apiFetch<{
        actionable: boolean;
        workflow_spec?: PlannedWorkflow | null;
        assistant_response: { reply_text: string };
      }>("/planner/plan", {
        method: "POST",
        body: JSON.stringify({
          request_text: planInput,
          client_capabilities: { runtime: "tauri", async: false },
          risk_tolerance: "high"
        })
      });
      if (!plan.actionable || !plan.workflow_spec) {
        setPlanned(null);
        setError(plan.assistant_response.reply_text);
        return;
      }
      setPlanned(plan.workflow_spec);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function savePlanned() {
    if (!planned) {
      return;
    }
    try {
      await apiFetch("/workflows/", {
        method: "POST",
        body: JSON.stringify({
          name: planned.name,
          description: "Created from planner in frontend",
          inputs: planned.inputs,
          nodes: planned.nodes,
          edges: planned.edges,
          outputs: planned.outputs,
          source_recipe_id: planned.source_recipe_id,
          risk_level: planned.risk_level,
          status: "pending",
          retry_policy: planned.retry_policy,
          confirm_points: planned.confirm_points,
          planner_decision_log: ["Saved via console"]
        })
      });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function updateStatus(id: number, status: ReviewStatus, risk_level: RiskLevel) {
    try {
      await apiFetch(`/workflows/${id}`, {
        method: "PUT",
        body: JSON.stringify({ status, risk_level })
      });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(id: number) {
    try {
      await apiFetch(`/workflows/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <section className="grid" style={{ gap: 16 }}>
      <article className="panel">
        <h2>Planner</h2>
        <form className="grid" style={{ gap: 10 }} onSubmit={createFromPlanner}>
          <textarea value={planInput} onChange={(e) => setPlanInput(e.target.value)} />
          <button type="submit">Generate Workflow Spec</button>
        </form>

        {planned ? (
          <div style={{ marginTop: 12 }}>
            <h3>{planned.name}</h3>
            <WorkflowGraph nodes={planned.nodes} edges={planned.edges} />
            <button onClick={savePlanned}>Save as Workflow</button>
            <pre className="code">{JSON.stringify(planned, null, 2)}</pre>
          </div>
        ) : null}

        {error ? <p className="small">{error}</p> : null}
      </article>

      <article className="panel">
        <h2>Workflow List</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Risk</th>
              <th>Status</th>
              <th>Nodes/Edges</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{item.name}</td>
                <td>{item.risk_level}</td>
                <td>{item.status}</td>
                <td>
                  {item.nodes.length}/{item.edges.length}
                </td>
                <td style={{ display: "flex", gap: 8 }}>
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
                  <button className="secondary" onClick={() => remove(item.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </section>
  );
}
