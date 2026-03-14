#!/usr/bin/env python3
"""Generate FastAPI CRUD router template."""

from __future__ import annotations

import argparse
from pathlib import Path


def render(resource: str, schema_name: str, model_name: str) -> str:
    plural = resource.lower()
    singular = plural[:-1] if plural.endswith("s") else plural

    return f'''from fastapi import APIRouter, Depends, HTTPException, status\nfrom sqlalchemy import select\nfrom sqlalchemy.orm import Session\n\nfrom app.core.database import get_db\nfrom app.models.{singular} import {model_name}\nfrom app.schemas.{singular}_schema import {schema_name}Create, {schema_name}Read, {schema_name}Update\n\nrouter = APIRouter(prefix="/{plural}", tags=["{plural}"])\n\n\n@router.get("/", response_model=list[{schema_name}Read])\ndef list_items(db: Session = Depends(get_db)):\n    return list(db.scalars(select({model_name})).all())\n\n\n@router.post("/", response_model={schema_name}Read, status_code=status.HTTP_201_CREATED)\ndef create_item(payload: {schema_name}Create, db: Session = Depends(get_db)):\n    item = {model_name}(**payload.model_dump(mode="json"))\n    db.add(item)\n    db.commit()\n    db.refresh(item)\n    return item\n\n\n@router.get("/{{item_id}}", response_model={schema_name}Read)\ndef get_item(item_id: int, db: Session = Depends(get_db)):\n    item = db.get({model_name}, item_id)\n    if not item:\n        raise HTTPException(status_code=404, detail="Not found")\n    return item\n\n\n@router.put("/{{item_id}}", response_model={schema_name}Read)\ndef update_item(item_id: int, payload: {schema_name}Update, db: Session = Depends(get_db)):\n    item = db.get({model_name}, item_id)\n    if not item:\n        raise HTTPException(status_code=404, detail="Not found")\n    for key, value in payload.model_dump(exclude_unset=True, mode="json").items():\n        setattr(item, key, value)\n    db.commit()\n    db.refresh(item)\n    return item\n\n\n@router.delete("/{{item_id}}")\ndef delete_item(item_id: int, db: Session = Depends(get_db)):\n    item = db.get({model_name}, item_id)\n    if not item:\n        raise HTTPException(status_code=404, detail="Not found")\n    db.delete(item)\n    db.commit()\n    return {{"deleted": True}}\n'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate FastAPI CRUD router template")
    parser.add_argument("--resource", required=True, help="plural resource name, e.g. skills")
    parser.add_argument("--schema", required=True, help="schema base name, e.g. SkillContract")
    parser.add_argument("--model", required=True, help="ORM model class, e.g. Skill")
    parser.add_argument("--out", required=True, help="output file")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output = Path(args.out)
    if output.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite existing file: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(args.resource, args.schema, args.model), encoding="utf-8")
    print(f"Generated CRUD API template: {output}")


if __name__ == "__main__":
    main()
