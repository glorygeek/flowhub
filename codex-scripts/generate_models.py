#!/usr/bin/env python3
"""Generate model templates for Pydantic and SQLAlchemy."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_fields(raw: str) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Invalid field format: {item}")
        name, field_type = item.split(":", 1)
        fields.append((name.strip(), field_type.strip()))
    if not fields:
        raise ValueError("No valid fields provided.")
    return fields


def pydantic_template(entity: str, fields: list[tuple[str, str]]) -> str:
    body = "\n".join([f"    {name}: {field_type}" for name, field_type in fields])
    return f'''from pydantic import BaseModel\n\n\nclass {entity}Base(BaseModel):\n{body}\n\n\nclass {entity}Create({entity}Base):\n    pass\n\n\nclass {entity}Read({entity}Base):\n    id: int\n'''


def sqlalchemy_template(entity: str, fields: list[tuple[str, str]]) -> str:
    mapped = []
    for name, field_type in fields:
        sql_type = "String"
        if field_type in {"int", "int | None"}:
            sql_type = "Integer"
        elif field_type in {"bool", "bool | None"}:
            sql_type = "Boolean"
        mapped.append(f"    {name}: Mapped[{field_type}] = mapped_column({sql_type})")
    body = "\n".join(mapped)
    table = entity.lower() + "s"
    return f'''from sqlalchemy import Boolean, Integer, String\nfrom sqlalchemy.orm import Mapped, mapped_column\n\nfrom app.core.database import Base\n\n\nclass {entity}(Base):\n    __tablename__ = "{table}"\n\n    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)\n{body}\n'''


def write_file(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate model template code.")
    parser.add_argument("--entity", required=True, help="Entity name, e.g. Skill")
    parser.add_argument("--fields", required=True, help="Comma-separated name:type pairs")
    parser.add_argument("--out", required=True, help="Output file path")
    parser.add_argument("--kind", choices=["pydantic", "sqlalchemy"], default="pydantic")
    parser.add_argument("--force", action="store_true", help="Overwrite existing file")
    args = parser.parse_args()

    fields = parse_fields(args.fields)
    entity = args.entity.strip()
    if not entity:
        raise ValueError("Entity must not be empty.")

    template = pydantic_template(entity, fields) if args.kind == "pydantic" else sqlalchemy_template(entity, fields)
    write_file(Path(args.out), template, args.force)
    print(f"Generated {args.kind} template at {args.out}")


if __name__ == "__main__":
    main()
