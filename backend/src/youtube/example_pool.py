import logging
import threading
from collections import deque
from collections.abc import Callable

from src.youtube.service import YoutubeSearchResult, YoutubeService

logger = logging.getLogger(__name__)

# One verified batch takes ~20 s on the mini-PC (a metadata call per video),
# so the pool is filled ahead of time and requests are served from it.
_TARGET_SIZE = 15
_REFILL_BELOW = 10
_BATCH_SIZE = 10
# Every round costs one metadata call per unseen hit; YouTube answers bursts with a bot check.
_MAX_ROUNDS_PER_REFILL = 2
# Served videos are remembered so "show others" never repeats one soon after.
_SERVED_MEMORY = 200


class ExamplePool:
    """Pre-verified YouTube suggestions, refilled in a background thread."""

    def __init__(self, service: YoutubeService) -> None:
        self._service = service
        self._items: list[YoutubeSearchResult] = []
        self._served: deque[str] = deque(maxlen=_SERVED_MEMORY)
        self._lock = threading.Lock()
        self._refilling = False

    def take(
        self, limit: int, is_known: Callable[[YoutubeSearchResult], bool]
    ) -> list[YoutubeSearchResult]:
        """Remove and return up to ``limit`` suggestions not yet in the library.

        Suggestions that became known since they were pooled are dropped.
        """
        taken: list[YoutubeSearchResult] = []
        with self._lock:
            while self._items and len(taken) < limit:
                item = self._items.pop()
                if is_known(item):
                    continue
                taken.append(item)
                self._served.append(item.video_id)
        self.refill_async()
        return taken

    def add(self, results: list[YoutubeSearchResult]) -> None:
        """Pool results fetched elsewhere, skipping duplicates and recently served ones."""
        with self._lock:
            self._add_locked(results)

    def refill_async(self) -> None:
        """Start a background refill unless the pool is full or one is already running."""
        with self._lock:
            if self._refilling or len(self._items) >= _REFILL_BELOW:
                return
            self._refilling = True
        threading.Thread(target=self._refill, name="youtube-example-pool", daemon=True).start()

    def _refill(self) -> None:
        try:
            for _ in range(_MAX_ROUNDS_PER_REFILL):
                with self._lock:
                    if len(self._items) >= _TARGET_SIZE:
                        break
                self.add(self._service.examples(_BATCH_SIZE))
            logger.info("[YouTube] Example pool holds %d suggestions", len(self._items))
        except Exception as exc:
            # A failed refill only means the next request fetches synchronously.
            logger.warning("[YouTube] Example pool refill failed: %s", exc)
        finally:
            with self._lock:
                self._refilling = False

    def _add_locked(self, results: list[YoutubeSearchResult]) -> None:
        present = {r.video_id for r in self._items} | set(self._served)
        for result in results:
            if result.video_id not in present:
                self._items.append(result)
                present.add(result.video_id)
