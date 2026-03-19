from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from autoqa_shared.artifact_storage import ArtifactStorage
from autoqa_shared.enums import RunStatus
from autoqa_shared.models import Artifact, DiscoveredFlow, FailureReport, GeneratedTest, RunStep, TestConfig, TestRun
from autoqa_shared.schemas import (
    ArtifactRead,
    DiscoveredFlowRead,
    FailureReportRead,
    RunCreate,
    RunDeleteRead,
    RunDetailRead,
    RunListItemRead,
    RunStepRead,
    TestRunRead,
)
from autoqa_shared.queue import RunQueue

from ...dependencies import get_db, get_queue

router = APIRouter(prefix="/runs", tags=["runs"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_run_or_404(db: Session, run_id: str) -> TestRun:
    run = db.scalar(select(TestRun).options(selectinload(TestRun.config)).where(TestRun.id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _delete_run_files(db: Session, run: TestRun) -> None:
    storage = ArtifactStorage()
    storage.delete_run_artifacts(run.id)
    generated_tests = list(run.generated_tests)
    for generated_test in generated_tests:
        duplicate_count = db.scalar(
            select(GeneratedTest.id).where(
                GeneratedTest.file_path == generated_test.file_path,
                GeneratedTest.id != generated_test.id,
            )
        )
        if duplicate_count is None:
            storage.delete_generated_test(generated_test.file_path)


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


@router.delete("/history", response_model=RunDeleteRead)
def clear_run_history(db: Session = Depends(get_db)) -> RunDeleteRead:
    runs = list(
        db.scalars(
            select(TestRun)
            .options(selectinload(TestRun.generated_tests))
            .where(TestRun.status.in_([RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.STOPPED.value]))
        ).all()
    )
    for run in runs:
        _delete_run_files(db, run)
        db.delete(run)
    db.commit()
    return RunDeleteRead(deleted_runs=len(runs))


@router.get("/{run_id}", response_model=RunDetailRead)
def get_run(run_id: str, db: Session = Depends(get_db)) -> TestRun:
    return _get_run_or_404(db, run_id)


@router.post("/{run_id}/pause", response_model=TestRunRead)
def pause_run(run_id: str, db: Session = Depends(get_db)) -> TestRun:
    run = _get_run_or_404(db, run_id)
    if run.status != RunStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="Only running runs can be paused")
    run.status = RunStatus.PAUSED.value
    run.error_message = None
    db.commit()
    db.refresh(run)
    return run


@router.post("/{run_id}/resume", response_model=TestRunRead)
def resume_run(run_id: str, db: Session = Depends(get_db)) -> TestRun:
    run = _get_run_or_404(db, run_id)
    if run.status != RunStatus.PAUSED.value:
        raise HTTPException(status_code=409, detail="Only paused runs can be resumed")
    run.status = RunStatus.RUNNING.value
    run.error_message = None
    db.commit()
    db.refresh(run)
    return run


@router.post("/{run_id}/stop", response_model=TestRunRead)
def stop_run(run_id: str, db: Session = Depends(get_db)) -> TestRun:
    run = _get_run_or_404(db, run_id)
    if run.status in {RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.STOPPED.value}:
        raise HTTPException(status_code=409, detail="Only active runs can be stopped")
    run.status = RunStatus.STOPPED.value
    run.error_message = "Run stopped by user."
    run.ended_at = _utcnow()
    db.commit()
    db.refresh(run)
    return run


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_run(run_id: str, db: Session = Depends(get_db)) -> Response:
    run = _get_run_or_404(db, run_id)
    if run.status in {RunStatus.RUNNING.value, RunStatus.PAUSED.value, RunStatus.QUEUED.value}:
        raise HTTPException(status_code=409, detail="Stop the run before deleting it")
    _delete_run_files(db, run)
    db.delete(run)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
