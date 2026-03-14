from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.common import ExecutionMode
from app.schemas.planner import PlannerPlanRequest, PlannerPlanResponse
from app.services.planner_engine import build_plan
from app.services.client_execution_guidance import build_client_execution_guidance

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
    return PlannerPlanResponse(
        actionable=plan_result.actionable,
        workflow_spec=plan_result.workflow_spec,
        decision_log=plan_result.decision_log,
        estimated_risk=plan_result.estimated_risk,
        assistant_response=plan_result.assistant_response,
        selected_skills=plan_result.selected_skills,
        communication_preview=plan_result.communication_preview,
        client_execution_guidance=build_client_execution_guidance(
            workflow_spec=plan_result.workflow_spec,
            selected_skills=plan_result.selected_skills,
        ),
    )
