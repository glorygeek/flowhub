#!/usr/bin/env python3
"""Generate a Next.js resource page template."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_fields(raw: str) -> list[str]:
    fields = [item.strip() for item in raw.split(",") if item.strip()]
    if not fields:
        raise ValueError("At least one field is required")
    return fields


def render(resource: str, fields: list[str]) -> str:
    field_inputs = "\n".join(
        [
            f'''          <input\n            placeholder="{field}"\n            value={{form.{field}}}\n            onChange={{(e) => setForm((p) => ({{ ...p, {field}: e.target.value }}))}}\n          />'''
            for field in fields
        ]
    )
    field_headers = "\n".join([f"              <th>{field}</th>" for field in fields])
    field_cells = "\n".join([f"                <td>{{item.{field}}}</td>" for field in fields])

    return f'''"use client";\n\nimport {{ FormEvent, useEffect, useState }} from "react";\nimport {{ apiFetch }} from "../lib/api";\n\ntype Item = Record<string, any>;\n\nexport default function {resource.title()}Page() {{\n  const [items, setItems] = useState<Item[]>([]);\n  const [form, setForm] = useState({{{", ".join([f"{field}: ''" for field in fields])}}});\n\n  async function load() {{\n    const data = await apiFetch<Item[]>("/{resource}/");\n    setItems(data);\n  }}\n\n  async function createItem(e: FormEvent) {{\n    e.preventDefault();\n    await apiFetch("/{resource}/", {{ method: "POST", body: JSON.stringify(form) }});\n    await load();\n  }}\n\n  useEffect(() => {{\n    void load();\n  }}, []);\n\n  return (\n    <section className="grid" style={{{{ gap: 16 }}}}>\n      <article className="panel">\n        <h2>Create {resource}</h2>\n        <form className="grid" onSubmit={{createItem}}>\n{field_inputs}\n          <button type="submit">Create</button>\n        </form>\n      </article>\n\n      <article className="panel">\n        <h2>{resource} list</h2>\n        <table>\n          <thead>\n            <tr>\n              <th>ID</th>\n{field_headers}\n            </tr>\n          </thead>\n          <tbody>\n            {{items.map((item) => (\n              <tr key={{item.id}}>\n                <td>{{item.id}}</td>\n{field_cells}\n              </tr>\n            ))}}\n          </tbody>\n        </table>\n      </article>\n    </section>\n  );\n}}\n'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate frontend page template")
    parser.add_argument("--resource", required=True, help="resource name")
    parser.add_argument("--fields", required=True, help="comma-separated fields")
    parser.add_argument("--out", required=True, help="output path")
    parser.add_argument("--force", action="store_true", help="overwrite existing file")
    args = parser.parse_args()

    output = Path(args.out)
    if output.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite existing file: {output}")

    content = render(args.resource, parse_fields(args.fields))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"Generated frontend page template: {output}")


if __name__ == "__main__":
    main()
