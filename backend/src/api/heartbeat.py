from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")

# Cloudflare drops a proxied response that stays silent for 100 s; a song
# analysis on the mini-PC can take longer than that.
HEARTBEAT_SECONDS = 20.0


def run_with_heartbeat(task: Callable[[], T], interval: float = HEARTBEAT_SECONDS) -> Iterator[T | None]:
    """Run ``task`` in a worker thread and yield ``None`` every ``interval``
    seconds while it is busy, then its result once.

    Lets a streaming response send keep-alive bytes during long work.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(task)
        while True:
            try:
                result = future.result(timeout=interval)
            except TimeoutError:
                yield None
                continue
            yield result
            return
