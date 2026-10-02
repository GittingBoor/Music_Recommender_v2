"""The one slot for the heavy part of the ingest: trimming and DSP/ML analysis.

Uploads, YouTube downloads and the bulk queue can all have audio ready at the
same time, e.g. when two visitors add a song at once. Only the holder of this
slot runs the trimmer or the analysis models; everyone else waits. The order is
fixed when a song asks for the slot (first come, first served), unlike a plain
``threading.Lock``, which wakes an arbitrary waiter.
"""
import itertools
import threading
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager


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
            self._cond.wait_for(lambda: not self._held and self._waiting[0] == ticket)
            self._waiting.popleft()
            self._held = True
        try:
            yield
        finally:
            with self._cond:
                self._held = False
                self._cond.notify_all()

    def locked(self) -> bool:
        """Whether a song holds the slot right now."""
        with self._cond:
            return self._held


processing_slot = ProcessingSlot()
