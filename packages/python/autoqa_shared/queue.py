import json
import time
from pathlib import Path

from redis import Redis
from redis.exceptions import RedisError

from .settings import get_settings


class LocalQueueStore:
    def __init__(self, queue_name: str) -> None:
        settings = get_settings()
        safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in queue_name)
        self.path = settings.artifacts_root / "reports" / f"{safe_name}.queue.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def ping(self) -> bool:
        return True

    def enqueue(self, run_id: str) -> None:
        items = self._read()
        items.insert(0, run_id)
        self._write(items)

    def dequeue(self, timeout: int) -> str | None:
        deadline = time.time() + max(timeout, 0)
        while True:
            items = self._read()
            if items:
                run_id = items.pop()
                self._write(items)
                return str(run_id)
            if time.time() >= deadline:
                return None
            time.sleep(0.2)

    def _read(self) -> list[str]:
        try:
            return list(json.loads(self.path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, items: list[str]) -> None:
        temp_path = Path(f"{self.path}.tmp")
        temp_path.write_text(json.dumps(items), encoding="utf-8")
        temp_path.replace(self.path)


class RunQueue:
    def __init__(self, url: str | None = None, queue_name: str | None = None) -> None:
        settings = get_settings()
        self.url = url or settings.redis_url
        self.queue_name = queue_name or settings.worker_queue_name
        self.client = Redis.from_url(self.url, decode_responses=True)
        self.local_store = LocalQueueStore(self.queue_name)

    def _use_local(self) -> bool:
        try:
            return not bool(self.client.ping())
        except RedisError:
            return True

    def ping(self) -> bool:
        if self._use_local():
            return self.local_store.ping()
        return bool(self.client.ping())

    def enqueue(self, run_id: str) -> None:
        if self._use_local():
            self.local_store.enqueue(run_id)
            return
        self.client.lpush(self.queue_name, run_id)

    def dequeue(self, timeout: int | None = None) -> str | None:
        settings = get_settings()
        poll_timeout = timeout if timeout is not None else settings.worker_poll_timeout
        if self._use_local():
            return self.local_store.dequeue(poll_timeout)
        item = self.client.brpop(self.queue_name, timeout=poll_timeout)
        if item is None:
            return None
        _, run_id = item
        return str(run_id)
