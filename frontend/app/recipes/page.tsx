"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import { Recipe, ReviewStatus, RiskLevel } from "../lib/types";

const statusOptions: ReviewStatus[] = ["draft", "pending", "approved", "rejected", "archived"];
const riskOptions: RiskLevel[] = ["low", "medium", "high"];

export default function RecipesPage() {
  const [items, setItems] = useState<Recipe[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "",
    scenario: "",
    description: "",
    risk_level: "low" as RiskLevel,
    status: "draft" as ReviewStatus,
    node_skeleton: '[{"id":"n1","skill_category":"analysis","config":{}}]',
    edges: "[]"
  });

  async function load() {
    setError("");
    try {
      const data = await apiFetch<Recipe[]>("/recipes/");
      setItems(data);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function createRecipe(e: FormEvent) {
    e.preventDefault();
    try {
      await apiFetch<Recipe>("/recipes/", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          tags: [],
          param_mappings: {},
          recommended_skill_categories: [],
          node_skeleton: JSON.parse(form.node_skeleton),
          edges: JSON.parse(form.edges)
        })
      });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function updateReview(item: Recipe) {
    const next = item.status === "approved" ? "pending" : "approved";
    try {
      await apiFetch<Recipe>(`/recipes/${item.id}`, {
        method: "PUT",
        body: JSON.stringify({ status: next })
      });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(id: number) {
    try {
      await apiFetch(`/recipes/${id}`, { method: "DELETE" });
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
        <h2>Create Recipe</h2>
        <form className="grid" onSubmit={createRecipe} style={{ gap: 10 }}>
          <input
            placeholder="name"
            value={form.name}
            onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            required
          />
          <input
            placeholder="scenario"
            value={form.scenario}
            onChange={(e) => setForm((prev) => ({ ...prev, scenario: e.target.value }))}
            required
          />
          <textarea
            placeholder="description"
            value={form.description}
            onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
          />
          <textarea
            placeholder="node_skeleton JSON"
            value={form.node_skeleton}
            onChange={(e) => setForm((prev) => ({ ...prev, node_skeleton: e.target.value }))}
          />
          <textarea
            placeholder="edges JSON"
            value={form.edges}
            onChange={(e) => setForm((prev) => ({ ...prev, edges: e.target.value }))}
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
          <button type="submit">Create Recipe</button>
        </form>
        {error ? <p className="small">{error}</p> : null}
      </article>

      <article className="panel">
        <h2>Recipe List</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Scenario</th>
              <th>Risk</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{item.name}</td>
                <td>{item.scenario}</td>
                <td>{item.risk_level}</td>
                <td>{item.status}</td>
                <td style={{ display: "flex", gap: 8 }}>
                  <button className="secondary" onClick={() => updateReview(item)}>
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
