import asyncio
import logging
import time

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


def main() -> None:
    settings = get_settings()
    queue = RunQueue()
    logger.info("worker started queue=%s redis=%s", settings.worker_queue_name, settings.redis_url)

    while True:
        run_id = queue.dequeue()
        if not run_id:
            continue

        logger.info("picked run_id=%s", run_id)
        db = SessionLocal()
        try:
            run = db.get(TestRun, run_id)
            if run is None:
                logger.info("skipping missing run_id=%s", run_id)
                continue
            if run.status != RunStatus.QUEUED.value:
                logger.info("skipping run_id=%s status=%s", run_id, run.status)
                continue
            engine = ExplorationEngine(db)
            asyncio.run(engine.run(run_id))
            logger.info("completed run_id=%s", run_id)
        except Exception:
            logger.exception("run execution failed run_id=%s", run_id)
            time.sleep(1)
        finally:
            db.close()


if __name__ == "__main__":
    main()
