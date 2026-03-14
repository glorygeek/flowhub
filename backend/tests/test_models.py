import pytest
from pydantic import ValidationError

from app.models.common import RiskLevel
from app.schemas.skill_contract import SkillContractCreate
from app.schemas.workflow_spec import WorkflowEdge, WorkflowNode, WorkflowSpec


def test_skill_contract_defaults():
    skill = SkillContractCreate(name="extract-text", category="ocr")
    assert skill.risk_level == RiskLevel.low
    assert skill.status.value == "draft"


def test_workflow_spec_accepts_valid_dag():
    spec = WorkflowSpec(
        name="valid",
        nodes=[
            WorkflowNode(id="n1", name="start"),
            WorkflowNode(id="n2", name="next"),
        ],
        edges=[WorkflowEdge(from_node="n1", to_node="n2")],
    )
    assert len(spec.nodes) == 2


def test_workflow_spec_rejects_cycle():
    with pytest.raises(ValidationError):
        WorkflowSpec(
            name="cycle",
            nodes=[
                WorkflowNode(id="n1", name="start"),
                WorkflowNode(id="n2", name="next"),
            ],
            edges=[
                WorkflowEdge(from_node="n1", to_node="n2"),
                WorkflowEdge(from_node="n2", to_node="n1"),
            ],
        )
