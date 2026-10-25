import json
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base, PlaylistImport, PlaylistImportTrack, User
from src.ingest import bulk
from src.ingest.bulk import BulkItem
from src.spotify.client import PlaylistSummary
from src.spotify.importer import PlaylistImporter
from src.spotify.matching import SpotifyTrack
from src.youtube.library_match import LibraryMatcher
from src.youtube.service import YoutubeSearchResult

_PLAYLIST = PlaylistSummary(id="pl1", name="Mix", image=None, track_count=3, owner="benni")


def _track(tid: str, title: str, *artists: str, seconds: int = 200) -> SpotifyTrack:
    return SpotifyTrack(spotify_id=tid, title=title, artists=artists, duration_ms=seconds * 1000, isrc=None)


def _hit(video_id: str, title: str, uploader: str, seconds: int) -> YoutubeSearchResult:
    return YoutubeSearchResult(video_id=video_id, title=title, uploader=uploader, duration=seconds,
                               thumbnail=None, url=f"https://youtu.be/{video_id}")


@pytest.fixture
def db_factory() -> Iterator[sessionmaker]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[User.__table__, PlaylistImport.__table__, PlaylistImportTrack.__table__])
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = factory()
    db.add(User(id=1, email="benni@example.de", password_hash="x"))
    db.commit()
    db.close()
    yield factory
    engine.dispose()


class Queue:
    def __init__(self) -> None:
        self.items: list[BulkItem] = []

    def __call__(self, items: list[BulkItem]) -> int:
        self.items.extend(items)
        return len(items)


def _importer(db_factory: sessionmaker, queue: Queue, library: list[tuple[str, str]] | None = None) -> PlaylistImporter:
    return PlaylistImporter(db_factory, queue, lambda db: LibraryMatcher(library or []))


def _rows(db_factory: sessionmaker) -> list[PlaylistImportTrack]:
    db = db_factory()
    try:
        return db.query(PlaylistImportTrack).order_by(PlaylistImportTrack.position).all()
    finally:
        db.close()


# --- importer -------------------------------------------------------------------

def test_start_marks_library_songs_duplicate(db_factory: sessionmaker) -> None:
    queue = Queue()
    tracks = [_track("t1", "Hello", "Adele"), _track("t2", "Hey Brother", "Avicii"), _track("t1", "Hello", "Adele")]
    import_id = _importer(db_factory, queue, library=[("Hello", "Adele")]).start(1, _PLAYLIST, tracks)

    rows = _rows(db_factory)
    assert [(r.spotify_track_id, r.status) for r in rows] == [("t1", "duplicate"), ("t2", "queued"), ("t1", "duplicate")]
    assert json.loads(rows[1].artists) == ["Avicii"]
    assert [i.expected.spotify_id for i in queue.items] == ["t2"]
    assert queue.items[0].query == "Avicii - Hey Brother"
    db = db_factory()
    assert db.get(PlaylistImport, import_id).name == "Mix"
    db.close()


def test_record_maps_results(db_factory: sessionmaker) -> None:
    queue = Queue()
    tracks = [_track("a", "A", "X"), _track("b", "B", "X"), _track("c", "C", "X")]
    importer = _importer(db_factory, queue)
    importer.start(1, _PLAYLIST, tracks)
    queue.items[0].on_done({"status": "saved", "reason": None, "song_id": "s1"}, "vid1")
    queue.items[1].on_done({"status": "skipped", "reason": "duplicate", "song_id": "s2"}, "vid2")
    queue.items[2].on_done({"status": "skipped", "reason": "spotify_mismatch", "song_id": None}, "vid3")

    rows = _rows(db_factory)
    assert [(r.status, r.reason, r.song_id, r.video_id) for r in rows] == [
        ("saved", None, "s1", "vid1"),
        ("duplicate", None, "s2", "vid2"),
        ("failed", "spotify_mismatch", None, "vid3"),
    ]


def test_resume_requeues_queued_tracks(db_factory: sessionmaker) -> None:
    first = Queue()
    _importer(db_factory, first).start(1, _PLAYLIST, [_track("a", "A", "X"), _track("b", "B", "Y")])
    first.items[0].on_done({"status": "saved", "song_id": "s1"}, "vid1")

    after_restart = Queue()
    assert _importer(db_factory, after_restart).resume() == 1
    assert [i.expected for i in after_restart.items] == [_track("b", "B", "Y")]
    after_restart.items[0].on_done({"status": "saved", "song_id": "s2"}, "vid2")
    assert [r.status for r in _rows(db_factory)] == ["saved", "saved"]


# --- bulk worker, Spotify path ----------------------------------------------------

@pytest.fixture
def failures(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict]]:
    recorded: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(bulk, "record_failure", lambda source, label, result, *a, **k: recorded.append((source, label, result)))
    return recorded


def _spotify_item(track: SpotifyTrack, done: list[tuple[dict, str | None]]) -> BulkItem:
    return BulkItem(query=track.query, label=track.query, expected=track, on_done=lambda r, v: done.append((r, v)))


def test_bulk_spotify_tries_next_candidate_on_mismatch(failures: list) -> None:
    track = _track("t1", "Hello", "Adele", seconds=295)
    hits = [
        _hit("cover", "Hello - Adele (Cover)", "Some Singer", 295),      # rejected before download
        _hit("right", "Adele - Hello (Official Video)", "AdeleVEVO", 300),
        _hit("wrong", "Adele - Hello", "Some Upload", 296),  # closest length, so tried first; AcoustID disagrees
    ]
    downloads: list[str] = []
    results = {"wrong": {"status": "skipped", "reason": "spotify_mismatch"}, "right": {"status": "saved", "song_id": "s1"}}

    def download(hit: YoutubeSearchResult, item: BulkItem, job_id: int) -> dict:
        downloads.append(hit.video_id)
        return results[hit.video_id]

    done: list[tuple[dict, str | None]] = []
    bulk._process_spotify(1, _spotify_item(track, done), lambda q, n: hits, download)
    assert downloads == ["wrong", "right"]
    assert done == [({"status": "saved", "song_id": "s1"}, "right")]
    assert failures == []


def test_bulk_spotify_without_fitting_hit_downloads_nothing(failures: list) -> None:
    track = _track("t1", "Hello", "Adele", seconds=295)
    hits = [_hit("other", "Lionel Richie - Hello", "LionelRichieVEVO", 295)]
    done: list[tuple[dict, str | None]] = []

    def download(hit: YoutubeSearchResult, item: BulkItem, job_id: int) -> dict:
        raise AssertionError("nothing should be downloaded")

    bulk._process_spotify(1, _spotify_item(track, done), lambda q, n: hits, download)
    assert done[0][0]["reason"] == "no_fitting_hit"
    assert done[0][1] is None
    assert failures[0][0] == "spotify" and failures[0][2]["reason"] == "no_fitting_hit"


def test_bulk_spotify_gives_up_after_three_candidates(failures: list) -> None:
    track = _track("t1", "Hello", "Adele", seconds=295)
    hits = [_hit(f"v{i}", "Adele - Hello", "Adele", 295) for i in range(5)]
    downloads: list[str] = []

    def download(hit: YoutubeSearchResult, item: BulkItem, job_id: int) -> dict:
        downloads.append(hit.video_id)
        return {"status": "skipped", "reason": "spotify_mismatch"}

    done: list[tuple[dict, str | None]] = []
    bulk._process_spotify(1, _spotify_item(track, done), lambda q, n: hits, download)
    assert downloads == ["v0", "v1", "v2"]
    assert done[0][0]["reason"] == "spotify_mismatch"
    assert failures[0][2]["reason"] == "spotify_mismatch"


# --- final review fixes -----------------------------------------------------------

def test_start_does_not_mistake_longer_title_for_library_song(db_factory: sessionmaker) -> None:
    queue = Queue()
    tracks = [_track("o", "Over My Dead Body", "Drake"), _track("r", "Intro (Reprise)", "The xx")]
    _importer(db_factory, queue, library=[("Over", "Drake"), ("Intro", "The xx")]).start(1, _PLAYLIST, tracks)
    assert [r.status for r in _rows(db_factory)] == ["queued", "queued"]


def test_failing_on_done_does_not_escape() -> None:
    def explode(result: dict, video_id: str | None) -> None:
        raise RuntimeError("database gone")

    BulkItem(query="q", label="q", on_done=explode).finish({"status": "saved"}, "v")


def test_record_keeps_exception_text_out_of_reason(db_factory: sessionmaker) -> None:
    queue = Queue()
    _importer(db_factory, queue).start(1, _PLAYLIST, [_track("a", "A", "X")])
    queue.items[0].on_done({"status": "error", "reason": "Traceback: connection reset by peer"}, None)
    assert _rows(db_factory)[0].reason == "error"


def test_spotify_items_go_before_bulk_and_survive_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    import queue as queue_module
    monkeypatch.setattr(bulk, "_queue", queue_module.PriorityQueue())
    monkeypatch.setattr(bulk, "_worker", object())  # pretend the worker runs, so nothing is consumed
    monkeypatch.setattr(bulk, "_ensure_worker", lambda: None)
    done: list[tuple[dict, str | None]] = []
    bulk.enqueue(["Chart Song 1", "Chart Song 2"])
    bulk.enqueue_items([_spotify_item(_track("t1", "Hello", "Adele"), done)])

    assert bulk.cancel_pending() == 2
    assert done == []
    _, _, _, item = bulk._queue.get_nowait()
    assert item.expected is not None
