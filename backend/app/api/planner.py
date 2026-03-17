from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.common import ExecutionMode
from app.schemas.planner import PlannerPlanRequest, PlannerPlanResponse
from app.services.client_install_guidance import build_client_install_guidance
from app.services.planner_engine import build_plan
from app.services.client_execution_guidance import build_client_execution_guidance
from app.services.workflow_summary import build_workflow_summary

router = APIRouter(prefix="/planner", tags=["planner"])


@router.post("/plan", response_model=PlannerPlanResponse)
def plan(payload: PlannerPlanRequest, db: Session = Depends(get_db)):
    plan_result = build_plan(
        goal=payload.request_text.strip(),
        targets=[],
        output_format="json",
        execution_mode=ExecutionMode.remote,
        risk_tolerance=payload.risk_tolerance,
        client_capabilities=payload.client_capabilities,
        db=db,
    )
    client_execution_guidance = build_client_execution_guidance(
        workflow_spec=plan_result.workflow_spec,
        selected_skills=plan_result.selected_skills,
    )
    client_install_guidance = (
        build_client_install_guidance(
            selected_skills=plan_result.selected_skills,
        )
        if plan_result.workflow_spec is not None
        else None
    )
    return PlannerPlanResponse(
        actionable=plan_result.actionable,
        workflow_spec=plan_result.workflow_spec,
        decision_log=plan_result.decision_log,
        estimated_risk=plan_result.estimated_risk,
        assistant_response=plan_result.assistant_response,
        selected_skills=plan_result.selected_skills,
        communication_preview=plan_result.communication_preview,
        client_execution_guidance=client_execution_guidance,
        client_install_guidance=client_install_guidance,
        workflow_summary=build_workflow_summary(
            workflow_spec=plan_result.workflow_spec,
            selected_skills=plan_result.selected_skills,
            assistant_response=plan_result.assistant_response,
            client_execution_guidance=client_execution_guidance,
        ),
    )
