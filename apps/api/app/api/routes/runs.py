from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autoqa_shared.models import Artifact, DiscoveredFlow, FailureReport, RunStep, TestConfig, TestRun
from autoqa_shared.schemas import (
    ArtifactRead,
    DiscoveredFlowRead,
    FailureReportRead,
    RunCreate,
    RunDetailRead,
    RunListItemRead,
    RunStepRead,
    TestRunRead,
)
from autoqa_shared.queue import RunQueue

from ...dependencies import get_db, get_queue

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=TestRunRead, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: RunCreate,
    db: Session = Depends(get_db),
    queue: RunQueue = Depends(get_queue),
) -> TestRun:
    config = db.get(TestConfig, payload.config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    run = TestRun(
        config_id=config.id,
        status="queued",
        max_steps=config.max_steps,
        safe_mode=config.safe_mode,
        run_settings={
            "target_url": config.target_url,
            "login_url": config.login_url,
            "headless": config.headless,
            "allowed_domains": config.allowed_domains,
        },
        summary={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    queue.enqueue(run.id)
    return run


@router.get("", response_model=list[RunListItemRead])
def list_runs(db: Session = Depends(get_db)) -> list[RunListItemRead]:
    runs = list(
        db.scalars(select(TestRun).options(selectinload(TestRun.config)).order_by(TestRun.created_at.desc())).all()
    )
    return [
        RunListItemRead(
            **TestRunRead.model_validate(run).model_dump(),
            config_name=run.config.name,
            target_url=run.config.target_url,
        )
        for run in runs
    ]


@router.get("/{run_id}", response_model=RunDetailRead)
def get_run(run_id: str, db: Session = Depends(get_db)) -> TestRun:
    run = db.scalar(select(TestRun).options(selectinload(TestRun.config)).where(TestRun.id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/steps", response_model=list[RunStepRead])
def list_run_steps(run_id: str, db: Session = Depends(get_db)) -> list[RunStep]:
    return list(db.scalars(select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.step_index.asc())).all())


@router.get("/{run_id}/flows", response_model=list[DiscoveredFlowRead])
def list_run_flows(run_id: str, db: Session = Depends(get_db)) -> list[DiscoveredFlow]:
    return list(db.scalars(select(DiscoveredFlow).where(DiscoveredFlow.run_id == run_id).order_by(DiscoveredFlow.created_at.asc())).all())


@router.get("/{run_id}/failures", response_model=list[FailureReportRead])
def list_run_failures(run_id: str, db: Session = Depends(get_db)) -> list[FailureReport]:
    return list(db.scalars(select(FailureReport).where(FailureReport.run_id == run_id).order_by(FailureReport.created_at.desc())).all())


@router.get("/{run_id}/artifacts", response_model=list[ArtifactRead])
def list_run_artifacts(run_id: str, db: Session = Depends(get_db)) -> list[Artifact]:
    return list(db.scalars(select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at.asc())).all())
