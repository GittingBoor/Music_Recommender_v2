from src.youtube.ranking import rank_entries


def _entry(video_id: str, title: str, channel: str, views: int, verified: bool | None = None) -> dict:
    return {"id": video_id, "title": title, "channel": channel, "view_count": views, "channel_is_verified": verified}


def _ids(entries: list[dict]) -> list[str]:
    return [e["id"] for e in entries]


def test_official_artist_channel_beats_fan_upload():
    fan = _entry("fan", "Metallica - Enter Sandman Live Moscow 1991 HD", "Met4life1995", 54_000_000)
    official = _entry("official", "Metallica: Enter Sandman (Official Music Video)", "Metallica", 50_000_000, True)
    assert _ids(rank_entries("Metallica - Enter Sandman", [fan, official])) == ["official", "fan"]


def test_unwanted_versions_rank_below_the_studio_version():
    live = _entry("live", "Metallica - Enter Sandman (Live in Mexico City)", "Metallica", 148_000_000, True)
    cover = _entry("cover", "Enter Sandman - Piano Cover", "PianoGuy", 90_000_000, True)
    studio = _entry("studio", "Enter Sandman (Remastered)", "Metallica", 55_000_000, True)
    assert _ids(rank_entries("Metallica - Enter Sandman", [live, cover, studio]))[0] == "studio"


def test_version_words_from_the_query_are_not_penalised():
    live = _entry("live", "Nirvana - Smells Like Teen Spirit (Live at Reading 1992)", "Nirvana", 80_000_000, True)
    studio = _entry("studio", "Nirvana - Smells Like Teen Spirit", "Nirvana", 60_000_000, True)
    assert _ids(rank_entries("Nirvana Smells Like Teen Spirit live", [studio, live]))[0] == "live"


def test_topic_channel_beats_popular_reupload():
    reupload = _entry("reupload", "Adele - Rolling In The Deep", "Music Lyrics HQ", 300_000_000)
    topic = _entry("topic", "Rolling in the Deep", "Adele - Topic", 20_000_000)
    assert _ids(rank_entries("Adele - Rolling in the Deep", [reupload, topic])) == ["topic", "reupload"]


def test_views_break_ties():
    few = _entry("few", "Daft Punk - Get Lucky", "Some Uploader", 1_000)
    many = _entry("many", "Daft Punk - Get Lucky", "Other Uploader", 5_000_000)
    assert _ids(rank_entries("Daft Punk - Get Lucky", [few, many])) == ["many", "few"]


def test_missing_counts_do_not_crash():
    bare = {"id": "bare", "title": "Song", "channel": None, "view_count": None}
    assert _ids(rank_entries("Song", [bare])) == ["bare"]
