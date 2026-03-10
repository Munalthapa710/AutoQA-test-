from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from autoqa_shared.queue import RunQueue
from autoqa_shared.schemas import HealthRead

from ...dependencies import get_db, get_queue

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthRead)
def healthcheck(db: Session = Depends(get_db), queue: RunQueue = Depends(get_queue)) -> HealthRead:
    database = "ok"
    redis = "ok"
    try:
        db.execute(text("select 1"))
    except Exception:
        database = "error"

    try:
        queue.ping()
    except Exception:
        redis = "error"

    overall = "ok" if database == "ok" and redis == "ok" else "degraded"
    return HealthRead(status=overall, database=database, redis=redis)
