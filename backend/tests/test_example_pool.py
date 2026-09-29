import threading

from src.youtube.example_pool import ExamplePool
from src.youtube.service import YoutubeSearchResult

_REFILL_TIMEOUT_SECONDS = 5.0


def _result(video_id: str, title: str = "Song") -> YoutubeSearchResult:
    return YoutubeSearchResult(
        video_id=video_id,
        title=title,
        uploader=None,
        duration=200,
        thumbnail=None,
        url=f"https://youtu.be/{video_id}",
    )


class _FakeService:
    """Hands out fresh numbered videos per call and counts the calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.called = threading.Event()

    def examples(self, limit: int = 5) -> list[YoutubeSearchResult]:
        self.calls += 1
        batch = [_result(f"v{self.calls}-{i}") for i in range(limit)]
        self.called.set()
        return batch


class _EmptyService:
    """YouTube returning nothing, so background refills don't change the pool."""

    def examples(self, limit: int = 5) -> list[YoutubeSearchResult]:
        return []


def _never_known(_: YoutubeSearchResult) -> bool:
    return False


def test_take_skips_songs_already_in_library() -> None:
    pool = ExamplePool(_EmptyService())
    pool.add([_result("a", "Known Song"), _result("b", "New Song")])

    taken = pool.take(5, lambda r: r.title == "Known Song")

    assert [r.video_id for r in taken] == ["b"]


def test_served_videos_are_not_pooled_again() -> None:
    pool = ExamplePool(_EmptyService())
    pool.add([_result("a")])
    pool.take(1, _never_known)

    pool.add([_result("a")])

    assert pool.take(1, _never_known) == []


def test_take_triggers_background_refill_when_low() -> None:
    service = _FakeService()
    pool = ExamplePool(service)

    pool.take(5, _never_known)

    assert service.called.wait(_REFILL_TIMEOUT_SECONDS)
