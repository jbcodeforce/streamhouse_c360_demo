"""FastAPI router for /scenarios — CEP controlled injection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from scenarios import service
from scenarios.models import ScenarioDefinition, ScenarioResult

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioDefinition], status_code=200)
def list_scenarios() -> list[ScenarioDefinition]:
    """Return all registered CEP scenario definitions."""
    return service.list_scenarios()


@router.post("/{scenario_id}/run", response_model=ScenarioResult, status_code=201)
def run_scenario(scenario_id: str) -> ScenarioResult:
    """Inject the scripted transaction sequence for a scenario.

    Returns the inserted Transaction rows so the caller can display an audit
    trail of what was injected.
    """
    try:
        return service.run(scenario_id)
    except service.UnknownScenarioError:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    except service.UnsupportedSinkError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Scenarios require SINK=postgres (current sink: {exc})",
        )
