from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.common import RiskLevel, ReviewStatus
from app.models.workflow import Workflow
from app.schemas.workflow_spec import WorkflowCreate, WorkflowRead, WorkflowUpdate

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/", response_model=list[WorkflowRead])
def list_workflows(
    db: Session = Depends(get_db),
    risk_level: RiskLevel | None = Query(default=None),
    status_filter: ReviewStatus | None = Query(default=None, alias="status"),
    source_recipe_id: int | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    query = select(Workflow)
    if risk_level:
        query = query.where(Workflow.risk_level == risk_level)
    if status_filter:
        query = query.where(Workflow.status == status_filter)
    if source_recipe_id is not None:
        query = query.where(Workflow.source_recipe_id == source_recipe_id)
    query = query.offset(skip).limit(limit)
    return list(db.scalars(query).all())


@router.post("/", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    workflow = Workflow(**payload.model_dump(mode="json"))
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowRead)
def update_workflow(workflow_id: int, payload: WorkflowUpdate, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    for field, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(workflow, field, value)
    db.commit()
    db.refresh(workflow)
    return workflow


@router.delete("/{workflow_id}")
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    db.delete(workflow)
    db.commit()
    return {"deleted": True, "id": workflow_id}
