from src.youtube.service import MusicVerdict, YoutubeService


class _FakeYoutube(YoutubeService):
    """Service with canned search hits and category verdicts instead of YouTube calls."""

    def __init__(self, entries: list[dict], verdicts: dict[str, MusicVerdict]) -> None:
        super().__init__()
        self._entries = entries
        self._canned = verdicts
        self.looked_up: list[str] = []

    def _flat_entries(self, target: str) -> list[dict]:
        return self._entries

    def _music_verdict(self, video_id: str, uploader: str | None) -> MusicVerdict:
        self.looked_up.append(video_id)
        return self._canned[video_id]


def _hit(video_id: str, channel: str, views: int, verified: bool = False) -> dict:
    return {"id": video_id, "title": f"Nirvana - Smells Like Teen Spirit {video_id}", "channel": channel,
            "duration": 300, "view_count": views, "channel_is_verified": verified}


def test_search_keeps_hits_whose_category_check_failed():
    service = _FakeYoutube([_hit("a", "Nirvana", 900, True)], {"a": MusicVerdict.UNKNOWN})
    assert [r.video_id for r in service.search("Nirvana - Smells Like Teen Spirit", 5)] == ["a"]


def test_search_drops_confirmed_non_music_and_ranks_the_rest():
    entries = [_hit("reupload", "Random", 10), _hit("vlog", "Vlogger", 999), _hit("official", "Nirvana", 5, True)]
    verdicts = {"reupload": MusicVerdict.MUSIC, "vlog": MusicVerdict.NOT_MUSIC, "official": MusicVerdict.MUSIC}
    service = _FakeYoutube(entries, verdicts)
    assert [r.video_id for r in service.search("Nirvana - Smells Like Teen Spirit", 5)] == ["official", "reupload"]


def test_search_only_checks_as_many_videos_as_it_needs():
    entries = [_hit(str(i), "Nirvana", 100 - i, True) for i in range(15)]
    service = _FakeYoutube(entries, {str(i): MusicVerdict.MUSIC for i in range(15)})
    assert len(service.search("Nirvana - Smells Like Teen Spirit", 5)) == 5
    assert len(service.looked_up) == 5
