import json
import threading
from pathlib import Path

import pytest

from src.ingest.slot import ProcessingSlot, processing_slot

_TIMEOUT = 5


def _wait_for_waiters(slot: ProcessingSlot, count: int) -> None:
    done = threading.Event()
    while not done.wait(0.01):
        with slot._cond:
            if len(slot._waiting) == count:
                done.set()


def test_only_one_song_holds_the_slot_and_the_rest_go_in_arrival_order():
    slot = ProcessingSlot()
    order: list[str] = []
    inside: list[int] = []
    release = threading.Event()

    def song(name: str) -> None:
        with slot.hold():
            inside.append(1)
            assert len(inside) == 1
            order.append(name)
            release.wait(_TIMEOUT)
            inside.pop()

    first = threading.Thread(target=song, args=("A",))
    first.start()
    while not slot.locked():
        pass
    waiters = []
    for count, name in enumerate(["B", "C", "D"], start=1):
        thread = threading.Thread(target=song, args=(name,))
        thread.start()
        _wait_for_waiters(slot, count)
        waiters.append(thread)

    release.set()
    for thread in [first, *waiters]:
        thread.join(_TIMEOUT)

    assert order == ["A", "B", "C", "D"]
    assert not slot.locked()


def test_the_slot_is_released_when_the_holder_fails():
    slot = ProcessingSlot()
    try:
        with slot.hold():
            raise ValueError("analysis crashed")
    except ValueError:
        pass
    assert not slot.locked()
    with slot.hold():
        assert slot.locked()


def test_a_youtube_song_holds_the_slot_from_trimming_to_the_end_of_the_analysis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from src.api.routes import youtube

    held: dict[str, bool] = {}
    downloaded = tmp_path / "raw.webm"
    downloaded.write_bytes(b"")

    class Trimmer:
        def trim_to(self, src: Path, dest: Path) -> bool:
            held["trim"] = processing_slot.locked()
            return False

    def process(audio: Path, job_id: int, hint: object, origin: object, slot_held: bool = False) -> dict:
        held["analysis"] = processing_slot.locked() and slot_held
        return {"status": "skipped", "reason": "test", "title": None, "artist": None, "song_id": None}

    monkeypatch.setattr(youtube, "_library_hit", lambda req: None)
    monkeypatch.setattr(youtube._service, "download_audio", lambda video_id, folder: downloaded)
    monkeypatch.setattr(youtube, "_YOUTUBE_DIR", tmp_path)
    monkeypatch.setattr(youtube, "get_music_trimmer", lambda: Trimmer())
    monkeypatch.setattr(youtube, "process_audio_file", process)

    req = youtube.YoutubeDownloadRequest(video_id="abc", title="Daft Punk - Get Lucky")
    events = [json.loads(line) for line in youtube._download_pipeline(req, log_failures=False)]

    assert events[-1]["stage"] == "done"
    assert held == {"trim": True, "analysis": True}
    assert not processing_slot.locked()
