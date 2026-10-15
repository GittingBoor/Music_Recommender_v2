"""The one slot for the heavy part of the ingest: trimming and DSP/ML analysis.

Uploads, YouTube downloads and the bulk queue can all have audio ready at the
same time, e.g. when two visitors add a song at once. Only the holder of this
slot runs the trimmer or the analysis models; everyone else waits. The order is
fixed when a song asks for the slot (first come, first served), unlike a plain
``threading.Lock``, which wakes an arbitrary waiter.

The host can pause the slot: while ``PAUSE_FILE`` exists (the mini-PC creates
it while its Minecraft server runs), no song gets the slot. The song holding it
finishes; uploads, downloads and the queues keep going and wait here.
"""
import itertools
import logging
import threading
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

PAUSE_FILE = Path("/run/musicrec-pause/paused")
# The flag is a file, not an event: re-check it this often while waiting.
_PAUSE_POLL_SECONDS = 5.0


def pipeline_paused() -> bool:
    """Whether the host has paused the heavy part of the ingest."""
    return PAUSE_FILE.exists()


class ProcessingSlot:
    """A first-come, first-served lock for one song at a time."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._tickets = itertools.count()
        self._waiting: deque[int] = deque()
        self._held = False

    @contextmanager
    def hold(self) -> Iterator[None]:
        """Wait for this song's turn and hold the slot for the ``with`` block."""
        with self._cond:
            ticket = next(self._tickets)
            self._waiting.append(ticket)
            self._wait_for_turn(ticket)
            self._waiting.popleft()
            self._held = True
        try:
            yield
        finally:
            with self._cond:
                self._held = False
                self._cond.notify_all()

    def _wait_for_turn(self, ticket: int) -> None:
        """Block (with the condition held) until ``ticket`` may take the slot."""
        logged_pause = False
        while not self._cond.wait_for(
            lambda: not self._held and self._waiting[0] == ticket and not pipeline_paused(),
            timeout=_PAUSE_POLL_SECONDS,
        ):
            if not logged_pause and not self._held and self._waiting[0] == ticket:
                logger.info("[Slot] Paused by the host, waiting for %s to disappear", PAUSE_FILE)
                logged_pause = True
        if logged_pause:
            logger.info("[Slot] Pause lifted, continuing")

    def locked(self) -> bool:
        """Whether a song holds the slot right now."""
        with self._cond:
            return self._held


processing_slot = ProcessingSlot()
