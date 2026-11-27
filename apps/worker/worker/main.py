import asyncio
import logging
import time

from redis.exceptions import RedisError
from sqlalchemy import select

from autoqa_shared.db import SessionLocal
from autoqa_shared.enums import RunStatus
from autoqa_shared.explorer import ExplorationEngine
from autoqa_shared.models import TestRun
from autoqa_shared.queue import RunQueue
from autoqa_shared.settings import get_settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("autoqa-worker")


def process_next_run(queue: RunQueue) -> bool:
    with SessionLocal() as db:
        try:
            run_id = queue.dequeue()
        except (RedisError, OSError):
            logger.warning("Queue temporarily unavailable, checking for pending runs in the database")
            run_id = None
        if not run_id:
            # The run row is committed before the queue notification is sent.
            run_id = db.scalar(
                select(TestRun.id)
                .where(TestRun.status == RunStatus.QUEUED.value)
                .order_by(TestRun.created_at, TestRun.id)
                .limit(1)
            )
        if not run_id:
            return False

        run = db.get(TestRun, run_id)
        if run is not None and run.status == RunStatus.QUEUED.value:
            logger.info("picked run_id=%s", run_id)
            asyncio.run(ExplorationEngine(db).run(run_id))
            logger.info("finished run_id=%s", run_id)
        return True


def main() -> None:
    settings = get_settings()
    queue = RunQueue()
    logger.info("worker started queue=%s", settings.worker_queue_name)
    while True:
        try:
            if not process_next_run(queue):
                time.sleep(0.2)
        except Exception:
            logger.exception("worker iteration failed")
            time.sleep(1)


if __name__ == "__main__":
    main()
