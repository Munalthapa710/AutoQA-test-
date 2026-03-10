from redis import Redis

from .settings import get_settings


class RunQueue:
    def __init__(self, url: str | None = None, queue_name: str | None = None) -> None:
        settings = get_settings()
        self.url = url or settings.redis_url
        self.queue_name = queue_name or settings.worker_queue_name
        self.client = Redis.from_url(self.url, decode_responses=True)

    def ping(self) -> bool:
        return bool(self.client.ping())

    def enqueue(self, run_id: str) -> None:
        self.client.lpush(self.queue_name, run_id)

    def dequeue(self, timeout: int | None = None) -> str | None:
        settings = get_settings()
        poll_timeout = timeout if timeout is not None else settings.worker_poll_timeout
        item = self.client.brpop(self.queue_name, timeout=poll_timeout)
        if item is None:
            return None
        _, run_id = item
        return str(run_id)
