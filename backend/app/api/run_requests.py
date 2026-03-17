import csv
import json
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.common import ReviewStatus
from app.models.run_request import RunRequest
from app.models.workflow import Workflow
from app.schemas.run_request import (
    CredentialDescriptor,
    RunRequestConfirmResponse,
    RunRequestCreate,
    RunRequestIntakeSummary,
    RunRequestPlanResponse,
    RunRequestRead,
)
from app.schemas.workflow_spec import WorkflowSpec
from app.services.planner_engine import (
    build_plan,
    build_response_bundle,
    resolve_workflow_skill_recommendations,
)
from app.services.client_execution_guidance import build_client_execution_guidance
from app.services.client_install_guidance import build_client_install_guidance
from app.services.workflow_summary import build_workflow_summary

router = APIRouter(prefix="/run-requests", tags=["run-requests"])


def mask_secret(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * max(len(value) - 4, 1)}{value[-2:]}"


def build_next_steps(execution_mode: str, output_format: str) -> list[str]:
    next_steps = [
        "Review the generated workflow, selected skills, and fetch instructions before execution.",
        "Use the returned skill list to pull dependencies from the official plugin center or Skill center.",
        f"Prepare downstream delivery for the requested {output_format} output.",
    ]
    if execution_mode == "local":
        next_steps.append("Let the client assemble the workflow locally and run it with client-side AI.")
    else:
        next_steps.append("Let the client fetch the skills, compose the workflow locally, and use client-side AI.")
    return next_steps


@router.post("", response_model=RunRequestPlanResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/", response_model=RunRequestPlanResponse, status_code=status.HTTP_201_CREATED)
def create_run_request(
    payload: RunRequestCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    planning_goal = payload.goal if not payload.user_notes else f"{payload.goal}\n{payload.user_notes}"
    plan = build_plan(
        goal=planning_goal,
        targets=[target.model_dump(mode="json") for target in payload.targets],
        output_format=payload.output_format,
        execution_mode=payload.execution_mode,
        risk_tolerance=None,
        client_capabilities={"surface": "web-intake"},
        db=db,
    )

    intake_summary = RunRequestIntakeSummary(
        target_count=len(payload.targets),
        credential_count=len(payload.credentials),
        output_format=payload.output_format,
        execution_mode=payload.execution_mode,
    )

    if not plan.actionable or plan.workflow_spec is None:
        response.status_code = status.HTTP_200_OK
        return RunRequestPlanResponse(
            actionable=False,
            request=None,
            workflow_spec=None,
            decision_log=plan.decision_log,
            next_steps=plan.assistant_response.usage_steps,
            intake_summary=intake_summary,
            assistant_response=plan.assistant_response,
            selected_skills=[],
            communication_preview=plan.communication_preview,
            client_execution_guidance=None,
            client_install_guidance=None,
            workflow_summary=None,
        )

    credential_descriptors = [
        CredentialDescriptor(
            label=item.label,
            kind=item.kind,
            preview=mask_secret(item.value),
            ephemeral=item.ephemeral,
        ).model_dump(mode="json")
        for item in payload.credentials
    ]

    workflow = Workflow(
        name=plan.workflow_spec.name,
        description="Generated from natural-language run request",
        inputs=plan.workflow_spec.inputs,
        nodes=[node.model_dump(mode="json") for node in plan.workflow_spec.nodes],
        edges=[edge.model_dump(mode="json") for edge in plan.workflow_spec.edges],
        outputs=plan.workflow_spec.outputs,
        source_recipe_id=plan.workflow_spec.source_recipe_id,
        risk_level=plan.workflow_spec.risk_level,
        status=ReviewStatus.pending,
        retry_policy=plan.workflow_spec.retry_policy,
        confirm_points=plan.workflow_spec.confirm_points,
        planner_decision_log=plan.decision_log,
    )
    db.add(workflow)
    db.flush()
    plan.workflow_spec.workflow_id = workflow.id

    record = RunRequest(
        goal=payload.goal,
        targets=[target.model_dump(mode="json") for target in payload.targets],
        credential_descriptors=credential_descriptors,
        output_format=payload.output_format,
        execution_mode=payload.execution_mode,
        user_notes=payload.user_notes,
        status="planned",
        workflow_spec=plan.workflow_spec.model_dump(mode="json"),
        planning_notes=plan.decision_log,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    client_execution_guidance = build_client_execution_guidance(
        workflow_spec=plan.workflow_spec,
        selected_skills=plan.selected_skills,
    )
    client_install_guidance = build_client_install_guidance(
        selected_skills=plan.selected_skills,
    )

    return RunRequestPlanResponse(
        actionable=True,
        request=RunRequestRead.model_validate(record),
        workflow_spec=plan.workflow_spec,
        decision_log=plan.decision_log,
        next_steps=build_next_steps(record.execution_mode.value, record.output_format),
        intake_summary=intake_summary,
        assistant_response=plan.assistant_response,
        selected_skills=plan.selected_skills,
        communication_preview=plan.communication_preview,
        client_execution_guidance=client_execution_guidance,
        client_install_guidance=client_install_guidance,
        workflow_summary=build_workflow_summary(
            workflow_spec=plan.workflow_spec,
            selected_skills=plan.selected_skills,
            assistant_response=plan.assistant_response,
            client_execution_guidance=client_execution_guidance,
        ),
    )


@router.get("", response_model=list[RunRequestRead], include_in_schema=False)
@router.get("/", response_model=list[RunRequestRead])
def list_run_requests(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
):
    query = select(RunRequest)
    if status_filter:
        query = query.where(RunRequest.status == status_filter)
    query = query.order_by(desc(RunRequest.created_at), desc(RunRequest.id)).limit(limit)
    return list(db.scalars(query).all())


@router.get("/export")
def export_run_requests(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    format: str = Query(default="jsonl", pattern="^(jsonl|csv)$"),
    limit: int = Query(default=200, ge=1, le=2000),
):
    query = select(RunRequest)
    if status_filter:
        query = query.where(RunRequest.status == status_filter)
    query = query.order_by(desc(RunRequest.created_at), desc(RunRequest.id)).limit(limit)
    items = list(db.scalars(query).all())

    if format == "csv":
        buffer = StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "id",
                "status",
                "goal",
                "workflow_id",
                "output_format",
                "execution_mode",
                "target_count",
                "credential_count",
                "created_at",
            ],
        )
        writer.writeheader()
        for item in items:
            workflow_id = item.workflow_spec.get("workflow_id") if isinstance(item.workflow_spec, dict) else None
            writer.writerow(
                {
                    "id": item.id,
                    "status": item.status,
                    "goal": item.goal,
                    "workflow_id": workflow_id,
                    "output_format": item.output_format,
                    "execution_mode": item.execution_mode.value,
                    "target_count": len(item.targets or []),
                    "credential_count": len(item.credential_descriptors or []),
                    "created_at": item.created_at.isoformat(),
                }
            )
        return PlainTextResponse(
            buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="run-requests.csv"'},
        )

    lines = []
    for item in items:
        lines.append(
            json.dumps(
                RunRequestRead.model_validate(item).model_dump(mode="json"),
                ensure_ascii=False,
            )
        )
    return PlainTextResponse(
        "\n".join(lines),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="run-requests.jsonl"'},
    )


@router.post("/{request_id}/confirm", response_model=RunRequestConfirmResponse)
def confirm_run_request(request_id: int, db: Session = Depends(get_db)):
    record = db.get(RunRequest, request_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run request not found")

    workflow_spec = WorkflowSpec.model_validate(record.workflow_spec)
    selected_skills = resolve_workflow_skill_recommendations(
        workflow_spec=workflow_spec,
        output_format=record.output_format,
        db=db,
    )
    assistant_response, communication_preview = build_response_bundle(
        goal=record.goal,
        output_format=record.output_format,
        execution_mode=record.execution_mode,
        workflow_spec=workflow_spec,
        selected_skills=selected_skills,
        communication_status="ready_to_send",
    )

    record.status = "queued"
    db.commit()
    db.refresh(record)

    client_execution_guidance = build_client_execution_guidance(
        workflow_spec=workflow_spec,
        selected_skills=selected_skills,
    )
    client_install_guidance = build_client_install_guidance(
        selected_skills=selected_skills,
    )

    return RunRequestConfirmResponse(
        request=RunRequestRead.model_validate(record),
        workflow_spec=workflow_spec,
        assistant_response=assistant_response,
        selected_skills=selected_skills,
        communication_preview=communication_preview,
        client_execution_guidance=client_execution_guidance,
        client_install_guidance=client_install_guidance,
        workflow_summary=build_workflow_summary(
            workflow_spec=workflow_spec,
            selected_skills=selected_skills,
            assistant_response=assistant_response,
            client_execution_guidance=client_execution_guidance,
        ),
    )
