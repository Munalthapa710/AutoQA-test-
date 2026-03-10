from collections.abc import Generator

from sqlalchemy.orm import Session

from autoqa_shared.db import get_db_session
from autoqa_shared.queue import RunQueue


def get_db() -> Generator[Session, None, None]:
    yield from get_db_session()


def get_queue() -> RunQueue:
    return RunQueue()
