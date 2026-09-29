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


def test_the_searched_song_beats_another_song_on_the_artist_channel():
    other = _entry("other", "DEICHKIND - So`ne Musik (OFFICIAL VIDEO)", "Deichkind", 20_000_000, True)
    wanted = _entry("wanted", "Deichkind - Remmidemmi (Yippie Yippie Yeah)", "deichkindTV", 15_000_000)
    assert _ids(rank_entries("Deichkind - Remmidemmi official audio", [other, wanted]))[0] == "wanted"


def test_accents_do_not_break_the_title_match():
    accented = _entry("accented", "Gymnopédie No. 1", "Erik Satie - Topic", 1_000_000)
    other = _entry("other", "Erik Satie - Gnossienne No. 1", "Erik Satie - Topic", 5_000_000)
    assert _ids(rank_entries("Erik Satie - Gymnopedie No. 1", [other, accented]))[0] == "accented"


def test_channel_named_after_the_song_gets_no_artist_bonus():
    junk = _entry("junk", "Beethoven - Moonlight Sonata ⚪ 432 Hz", "Moonlight Sonata", 30_000_000)
    real = _entry("real", "Beethoven - Moonlight Sonata (1st Movement)", "Rousseau", 20_000_000)
    assert _ids(rank_entries("Beethoven - Moonlight Sonata", [junk, real]))[0] == "real"


def test_concert_recordings_and_other_versions_rank_below_the_studio_version():
    concert = _entry("concert", "Simon & Garfunkel - The Sound of Silence (from The Concert in Central Park)",
                     "Simon & Garfunkel", 90_000_000, True)
    studio = _entry("studio", "Simon & Garfunkel - The Sound of Silence (Audio)", "Simon & Garfunkel", 60_000_000, True)
    assert _ids(rank_entries("Simon & Garfunkel - The Sound of Silence", [concert, studio]))[0] == "studio"

    orchestra = _entry("orchestra", "Hans Zimmer - Inception: Time - Orchestra Version", "Hans Zimmer", 50_000_000, True)
    original = _entry("original", "Time", "Hans Zimmer - Topic", 40_000_000)
    assert _ids(rank_entries("Hans Zimmer - Time", [orchestra, original]))[0] == "original"


def test_concert_film_titles_rank_below_the_studio_video():
    film = _entry("film", "Rammstein: Paris - Du Hast (Official Video)", "Rammstein Official", 200_000_000, True)
    studio = _entry("studio", "Rammstein - Du Hast (Official 4K Video)", "Rammstein Official", 90_000_000, True)
    assert _ids(rank_entries("Rammstein - Du Hast", [film, studio]))[0] == "studio"


def test_video_about_the_searched_artist_beats_a_popular_video_of_another_artist():
    chopin = _entry("chopin", "Chopin - Spring Waltz (Mariage d'Amour)", "Toms Mucenieks", 200_000_000)
    vivaldi = _entry("vivaldi", "Vivaldi - Spring (The Four Seasons)", "Rousseau", 20_000_000)
    assert _ids(rank_entries("Vivaldi - Spring", [chopin, vivaldi]))[0] == "vivaldi"
