from pathlib import Path

from src.metadata.musicbrainz import (
    RecordingIdentity,
    album_from_search,
    canonical_from_search,
    performed_work_ids,
    pick_album,
    recording_identity,
    work_composers,
)


def _release(
    rg_id: str, title: str, rg_type: str, date: str | None, status: str = "Official",
    secondary: list[str] | None = None,
) -> dict:
    return {"title": title, "date": date, "status": status,
            "release-group": {"id": rg_id, "title": title, "primary-type": rg_type,
                              "secondary-types": secondary or []}}


def test_earliest_official_album_wins_over_singles_and_compilations():
    releases = [
        _release("single", "Get Lucky", "Single", "2013-04-19"),
        _release("best-of", "Now That's What I Call Music", "Album", "2012-01-01", status="Bootleg"),
        _release("ram-reissue", "Random Access Memories", "Album", "2023-11-17"),
        _release("ram", "Random Access Memories", "Album", "2013-05-17"),
    ]
    assert pick_album(releases) == ("ram", "Random Access Memories")


def test_single_is_used_when_the_song_is_on_no_album():
    releases = [_release("single", "Remmidemmi", "Single", "2006-06-02")]
    assert pick_album(releases) == ("single", "Remmidemmi")


def test_no_releases_means_no_album():
    assert pick_album([]) == (None, None)


def _credit(name: str, join: str = "") -> dict:
    return {"name": name, "joinphrase": join, "artist": {"name": name}}


def test_recording_identity_splits_main_and_featured_artists():
    rec = {"title": "Get Lucky", "artist-credit": [_credit("Daft Punk", " feat. "), _credit("Pharrell Williams")]}
    assert recording_identity(rec) == RecordingIdentity(
        title="Get Lucky", artist="Daft Punk", featured_artists=["Pharrell Williams"]
    )


def test_recording_identity_needs_title_and_artist():
    assert recording_identity({"title": "So What", "artist-credit": []}) is None
    assert recording_identity({"artist-credit": [_credit("Miles Davis")]}) is None


def test_recording_lookup_asks_for_release_groups(monkeypatch):
    from src.metadata import musicbrainz

    requested: list[str] = []

    def fake_get(path: str, params: dict[str, str]) -> dict | None:
        requested.append(params.get("inc", ""))
        if path.startswith("recording/"):
            return {"releases": [_release("ram", "Random Access Memories", "Album", "2013-05-17")]}
        return {}

    monkeypatch.setattr(musicbrainz, "_mb_json_get", fake_get)
    data = musicbrainz._get_recording_data("rec-1")

    assert "release-groups" in requested[0].split("+")
    assert data["album_mbid"] == "ram"


def test_recording_identity_drops_version_markers():
    rec = {"title": "Wake Me Up (Radio Edit)", "artist-credit": [_credit("Avicii")]}
    identity = recording_identity(rec)
    assert identity is not None and identity.title == "Wake Me Up"


def test_live_albums_and_compilations_are_not_the_album():
    releases = [
        _release("live", "Live Sh*t", "Album", "1993-11-23", secondary=["Live"]),
        _release("hits", "The 100 Collection: 90s", "Album", "1990-01-01", secondary=["Compilation"]),
        _release("single", "Enter Sandman", "Single", "1991-07-29"),
        _release("black", "Metallica", "Album", "1991-08-12"),
    ]
    assert pick_album(releases) == ("black", "Metallica")


def test_only_live_or_compilation_releases_mean_no_album():
    releases = [_release("live", "Live Sh*t", "Album", "1993-11-23", secondary=["Live"])]
    assert pick_album(releases) == (None, None)


def test_performed_works_and_their_composers_are_read():
    rec = {"relations": [
        {"target-type": "work", "type": "performance", "work": {"id": "w1", "title": "Première Gymnopédie"}},
        {"target-type": "url", "type": "free streaming", "url": {"resource": "https://example.org"}},
    ]}
    work = {"relations": [
        {"target-type": "artist", "type": "composer", "artist": {"name": "Erik Satie"}},
        {"target-type": "artist", "type": "lyricist", "artist": {"name": "Somebody"}},
    ]}
    assert performed_work_ids(rec) == ["w1"]
    assert work_composers(work) == ["Erik Satie"]


def _search_hit(title: str, artist: str, releases: list[dict]) -> dict:
    return {"title": title, "score": 100, "artist-credit": [{"name": artist, "artist": {"name": artist}}],
            "releases": releases}


def test_album_of_the_song_comes_from_all_its_recordings():
    search = {"recordings": [
        _search_hit("Enter Sandman", "Metallica", [_release("load", "Load", "Album", "1996-06-04")]),
        _search_hit("Enter Sandman", "Metallica", [
            _release("single", "Enter Sandman", "Single", "1991-07-29"),
            _release("black", "Metallica", "Album", "1991-08-12"),
        ]),
        _search_hit("Enter Sandman", "Motörhead", [_release("cover", "Covers", "Album", "1980-01-01")]),
        _search_hit("Exit Light", "Metallica", [_release("other", "Other", "Album", "1985-01-01")]),
    ]}
    assert album_from_search(search, "Enter Sandman", "Metallica") == ("black", "Metallica")


def test_album_search_ignores_version_markers_and_case():
    search = {"recordings": [
        _search_hit("Get Lucky (radio edit)", "Daft Punk", [_release("ram", "Random Access Memories", "Album", "2013-05-17")]),
    ]}
    assert album_from_search(search, "get lucky", "daft punk") == ("ram", "Random Access Memories")


def test_album_search_without_matching_recordings():
    assert album_from_search({"recordings": []}, "Song", "Artist") == (None, None)


def test_the_album_the_song_was_released_on_most_often_wins_over_an_earlier_one_off():
    black = [_release("black", "Metallica", "Album", d) for d in ("1991-08-12", "2021-09-10", "2022-01-01")]
    search = {"recordings": [
        _search_hit("Enter Sandman", "Metallica", [_release("tosox", "TosoX Episode 3", "Album", "1991-03-01")]),
        _search_hit("Enter Sandman", "Metallica", black),
    ]}
    assert album_from_search(search, "Enter Sandman", "Metallica") == ("black", "Metallica")


def test_compilations_mislabelled_as_albums_are_skipped():
    releases = [
        _release("sampler", "101 Great Orchestral Classics, Volume 9", "Album", "1975"),
        _release("hits", "Legend: The Best of Bob Marley", "Album", "1979-05-08"),
        _release("uprising", "Uprising", "Album", "1980-06-10"),
    ]
    assert pick_album(releases) == ("uprising", "Uprising")


def test_musicbrainz_is_asked_again_when_it_is_busy(monkeypatch):
    import io
    import urllib.error

    from src.metadata import musicbrainz

    calls: list[str] = []

    def fake_urlopen(req, timeout: float):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 503, "Service Temporarily Unavailable", {}, io.BytesIO(b""))
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(musicbrainz.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(musicbrainz.time, "sleep", lambda _s: None)

    assert musicbrainz._mb_json_get("recording/x", {}) == {"ok": True}
    assert len(calls) == 2


def _credited_hit(title: str, *artists: str) -> dict:
    return {"title": title, "score": 100, "artist-credit": [{"name": a, "artist": {"name": a}} for a in artists]}


def test_canonical_recording_splits_a_comma_joined_artist_into_artist_and_featured():
    search = {"recordings": [_credited_hit("Shallow", "Lady Gaga", "Bradley Cooper")]}
    assert canonical_from_search(search, "Shallow", "Lady Gaga, Bradley Cooper") == RecordingIdentity(
        title="Shallow", artist="Lady Gaga", featured_artists=["Bradley Cooper"]
    )


def test_canonical_recording_keeps_band_names_whole_and_fixes_spelling():
    search = {"recordings": [
        _credited_hit("The Sound of Silence", "Simon & Garfunkel"),
        _credited_hit("September", "Earth, Wind & Fire"),
    ]}
    assert canonical_from_search(search, "the sound of silence", "Simon & Garfunkel") == RecordingIdentity(
        title="The Sound of Silence", artist="Simon & Garfunkel", featured_artists=[]
    )
    assert canonical_from_search(search, "September", "Earth, Wind & Fire") == RecordingIdentity(
        title="September", artist="Earth, Wind & Fire", featured_artists=[]
    )


def test_no_canonical_recording_for_another_artist_or_title():
    search = {"recordings": [
        _credited_hit("Gymnopédie No. 1", "Philippe Entremont"),
        _credited_hit("Stronger (Remix)", "Kanye West"),
    ]}
    assert canonical_from_search(search, "Gymnopédie No. 1", "Erik Satie") is None
    assert canonical_from_search(search, "Stronger Than Ever", "Kanye West") is None


def _credited_release(rg_id: str, title: str, rg_type: str, date: str, release_artist: str) -> dict:
    rel = _release(rg_id, title, rg_type, date)
    rel["artist-credit"] = [{"name": release_artist, "artist": {"name": release_artist}}]
    return rel


def test_only_albums_of_the_songs_main_artist_count():
    search = {"recordings": [_search_hit("One Kiss", "Calvin Harris", [
        _credited_release("sampler", "Deep Dance 157", "Album", "2018-05-01", "Various Artists"),
        _credited_release("dua", "Dua Lipa", "Album", "2018-10-19", "Dua Lipa"),
        _credited_release("dua", "Dua Lipa", "Album", "2019-01-01", "Dua Lipa"),
        _credited_release("single", "One Kiss", "Single", "2018-04-06", "Calvin Harris"),
    ])]}
    assert album_from_search(search, "One Kiss", "Calvin Harris") == ("single", "One Kiss")


def test_canonical_prefers_the_exact_spelling():
    search = {"recordings": [
        _credited_hit("Gymnopedie No. 1", "Erik Satie"),
        _credited_hit("Gymnopédie No. 1", "Erik Satie"),
    ]}
    identity = canonical_from_search(search, "Gymnopédie No. 1", "Erik Satie")
    assert identity is not None and identity.title == "Gymnopédie No. 1"


def test_recording_identity_uses_plain_quotes():
    identity = recording_identity({"title": "Hips Don’t Lie", "artist-credit": [_credit("Shakira")]})
    assert identity is not None and identity.title == "Hips Don't Lie"


def _person_hit(title: str, name: str, sort_name: str) -> dict:
    return {"title": title, "score": 100,
            "artist-credit": [{"name": name, "artist": {"name": name, "sort-name": sort_name}}]}


def test_canonical_matches_a_composer_by_surname():
    search = {"recordings": [_person_hit("Moonlight Sonata", "Ludwig van Beethoven", "Beethoven, Ludwig van")]}
    identity = canonical_from_search(search, "Moonlight Sonata", "Beethoven")
    assert identity is not None and identity.artist == "Ludwig van Beethoven"


def test_a_band_ending_in_the_surname_is_not_that_person():
    search = {"recordings": [
        _person_hit("Moonlight Sonata", "Electric Beethoven", "Electric Beethoven"),
        _person_hit("Moonlight Sonata", "Ludwig van Beethoven", "Beethoven, Ludwig van"),
    ]}
    identity = canonical_from_search(search, "Moonlight Sonata", "Beethoven")
    assert identity is not None and identity.artist == "Ludwig van Beethoven"


def test_song_album_search_adds_a_narrower_query_only_when_results_are_cut_off(monkeypatch):
    from src.metadata import musicbrainz

    black = [_release("black", "Metallica", "Album", "1991-08-12")] * 3
    reload_ = [_release("reload", "Reload", "Album", "1997-11-18")]
    live_heavy = {"count": 532, "recordings": [
        dict(_search_hit("Enter Sandman", "Metallica", reload_), id="r-reload"),
    ]}
    narrow = {"count": 38, "recordings": [
        dict(_search_hit("Enter Sandman", "Metallica", reload_), id="r-reload"),
        dict(_search_hit("Enter Sandman", "Metallica", black), id="r-black"),
    ]}
    queries: list[str] = []

    def fake_get(path: str, params: dict[str, str]) -> dict:
        if path.startswith("release-group/"):
            return {}
        queries.append(params["query"])
        return narrow if "NOT secondarytype" in params["query"] else live_heavy

    monkeypatch.setattr(musicbrainz, "_mb_json_get", fake_get)
    assert musicbrainz.fetch_song_album("Enter Sandman", "Metallica") == ("black", "Metallica")
    assert len(queries) == 2

    queries.clear()
    small = {"count": 1, "recordings": [dict(_search_hit("In the End", "Linkin Park", black), id="r-lp")]}

    def small_get(path: str, params: dict[str, str]) -> dict:
        if path.startswith("release-group/"):
            return {}
        queries.append(params["query"])
        return small

    monkeypatch.setattr(musicbrainz, "_mb_json_get", small_get)
    musicbrainz.fetch_song_album("In the End", "Linkin Park")
    assert len(queries) == 1 and "NOT secondarytype" not in queries[0]


def test_albums_released_years_after_the_song_are_not_its_album():
    search = {"recordings": [_search_hit("One Kiss", "Calvin Harris", [
        _release("single", "One Kiss", "Single", "2018-04-06"),
        _release("best", "96 Months", "Album", "2024-08-02"),
        _release("best", "96 Months", "Album", "2024-09-01"),
    ])]}
    assert album_from_search(search, "One Kiss", "Calvin Harris") == ("single", "One Kiss")

    game = [
        _release("own", "Lose Yourself", "Single", "2002-10-28"),
        _release("game", "DJ Hero: Renegade Edition", "Album", "2010-10-26", secondary=["Soundtrack"]),
    ]
    assert pick_album(game) == ("own", "Lose Yourself")


def test_the_original_album_beats_a_more_released_later_one():
    search = {"recordings": [_search_hit("The Sounds of Silence", "Simon & Garfunkel", [
        _release("wm3", "Wednesday Morning, 3 A.M.", "Album", "1964-10-19"),
        *[_release("sos", "Sounds of Silence", "Album", f"19{y}-01-17") for y in (66, 70, 90)],
    ])]}
    assert album_from_search(search, "The Sounds of Silence", "Simon & Garfunkel") == (
        "wm3", "Wednesday Morning, 3 A.M."
    )


def test_parallel_lookups_never_hit_musicbrainz_at_the_same_time(monkeypatch):
    import io
    import threading
    import time as real_time

    from src.metadata import musicbrainz

    active = 0
    overlap = False
    guard = threading.Lock()

    def fake_urlopen(req, timeout: float):
        nonlocal active, overlap
        with guard:
            active += 1
            overlap = overlap or active > 1
        real_time.sleep(0.05)
        with guard:
            active -= 1
        return io.BytesIO(b"{}")

    monkeypatch.setattr(musicbrainz.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(musicbrainz, "_MB_MIN_INTERVAL_SECONDS", 0.0)
    threads = [threading.Thread(target=musicbrainz._mb_json_get, args=("recording/x", {})) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not overlap


def test_classical_samplers_are_not_albums():
    releases = [_release("sampler", "Klassik: Die schönste klassische Musik", "Album", "2015-01-01")]
    assert pick_album(releases) == (None, None)


def test_soundtracks_only_count_for_fingerprinted_songs():
    search = {"recordings": [_search_hit("Spring", "Antonio Vivaldi", [
        _release("game", "Mario & Sonic Original Soundtrack", "Album", "2009-10-13", secondary=["Soundtrack"]),
        _release("game", "Mario & Sonic Original Soundtrack", "Album", "2009-11-13", secondary=["Soundtrack"]),
    ])]}
    assert album_from_search(search, "Spring", "Antonio Vivaldi", allow_soundtracks=False) == (None, None)
    assert album_from_search(search, "Spring", "Antonio Vivaldi") == ("game", "Mario & Sonic Original Soundtrack")


def test_an_artist_credited_under_an_old_name_still_counts():
    credit = [{"name": "Kanye West", "artist": {"name": "Ye", "sort-name": "Ye"}}]
    release = _release("grad", "Graduation", "Album", "2007-09-11")
    release["artist-credit"] = credit
    search = {"recordings": [{"title": "Stronger", "score": 100, "artist-credit": credit, "releases": [release]}]}
    assert album_from_search(search, "Stronger", "Kanye West") == ("grad", "Graduation")


def test_recording_identity_uses_the_credited_name():
    rec = {"title": "Stronger", "artist-credit": [{"name": "Kanye West", "artist": {"name": "Ye", "sort-name": "Ye"}}]}
    identity = recording_identity(rec)
    assert identity is not None and identity.artist == "Kanye West"


def test_canonical_prefers_the_full_artist_over_its_first_name():
    search = {"recordings": [
        _credited_hit("Could You Be Loved", "Bob Marley"),
        _credited_hit("Could You Be Loved", "Bob Marley & The Wailers"),
    ]}
    identity = canonical_from_search(search, "Could You Be Loved", "Bob Marley & The Wailers")
    assert identity is not None and identity.artist == "Bob Marley & The Wailers"


def test_canonical_prefers_the_exact_case():
    search = {"recordings": [_credited_hit("7 Rings", "Ariana Grande"), _credited_hit("7 rings", "Ariana Grande")]}
    identity = canonical_from_search(search, "7 rings", "Ariana Grande")
    assert identity is not None and identity.title == "7 rings"


def test_the_album_window_uses_the_groups_first_release_date():
    search = {"recordings": [_search_hit("Enter Sandman", "Metallica", [
        _release("single", "Enter Sandman", "Single", "1991-07-29"),
        _release("black", "Metallica", "Album", "2008-01-01"),
        _release("black", "Metallica", "Album", "2021-09-10"),
    ])]}
    first_release = {"single": "1991-07-29", "black": "1991-08-12"}
    assert album_from_search(search, "Enter Sandman", "Metallica", first_release=first_release) == (
        "black", "Metallica"
    )


def test_a_one_off_album_is_not_enough_when_the_song_is_unconfirmed():
    search = {"recordings": [_search_hit("Nocturne op.9 No.2", "Chopin", [
        _release("junk", "Nocturnes", "Album", "2019-01-01"),
    ])]}
    assert album_from_search(search, "Nocturne op.9 No.2", "Chopin", min_releases=2) == (None, None)
    assert album_from_search(search, "Nocturne op.9 No.2", "Chopin") == (
        "junk", "Nocturnes"
    )


def test_non_latin_names_of_people_use_their_latin_sort_name():
    rec = {"title": "Swan Lake", "artist-credit": [{"name": "Пётр Ильич Чайковский", "artist": {
        "name": "Пётр Ильич Чайковский", "sort-name": "Tchaikovsky, Pyotr Ilyich"}}]}
    identity = recording_identity(rec)
    assert identity is not None and identity.artist == "Pyotr Ilyich Tchaikovsky"
    rosalia = {"title": "DESPECHÁ", "artist-credit": [{"name": "ROSALÍA", "artist": {"name": "ROSALÍA", "sort-name": "ROSALÍA"}}]}
    assert recording_identity(rosalia).artist == "ROSALÍA"


def test_composers_in_another_script_get_their_latin_name():
    work = {"relations": [{"target-type": "artist", "type": "composer", "artist": {
        "name": "Пётр Ильич Чайковский", "sort-name": "Tchaikovsky, Pyotr Ilyich"}}]}
    assert work_composers(work) == ["Pyotr Ilyich Tchaikovsky"]


def test_text_search_only_uses_recordings_of_the_same_artist(monkeypatch):
    from src.metadata import musicbrainz

    search = {"recordings": [
        dict(_person_hit("Moonlight Sonata", "Electric Beethoven", "Electric Beethoven"), id="band"),
        dict(_person_hit("Moonlight Sonata", "Ludwig van Beethoven", "Beethoven, Ludwig van"), id="ludwig"),
    ]}
    monkeypatch.setattr(musicbrainz, "_mb_json_get", lambda path, params: search)
    assert musicbrainz._search_recording_ids("Moonlight Sonata", "Beethoven") == ["ludwig"]


def test_featured_artists_come_only_from_the_identified_recording(monkeypatch):
    from src.metadata import musicbrainz

    data = {
        "rec-a": {"genres": [], "release_date": None, "featured_artists": ["Patrick Cohen"],
                  "album_mbid": None, "album": None},
        "rec-b": {"genres": ["classical"], "release_date": None, "featured_artists": ["Philippe Entremont"],
                  "album_mbid": None, "album": None},
    }
    monkeypatch.setattr(musicbrainz, "_get_recording_data", lambda rid: dict(data[rid]))
    monkeypatch.setattr(musicbrainz, "_search_recording_ids", lambda title, artist: ["rec-b"])

    result = musicbrainz.fetch_musicbrainz_data(
        Path("x.mp3"), "", title="Gymnopédie", artist="Erik Satie",
        prefetched_recording_id="rec-a", acoustid_done=True,
    )
    assert result["featured_artists"] == ["Patrick Cohen"]
    assert result["genres"] == ["classical"]


def test_real_albums_with_a_volume_number_count():
    releases = [
        _release("single", "Hips Don't Lie", "Single", "2006-04-01"),
        _release("oral", "Oral Fixation Vol. 2", "Album", "2005-11-28"),
    ]
    assert pick_album(releases) == ("oral", "Oral Fixation Vol. 2")


def test_soundtracks_count_as_the_album():
    releases = [_release("ost", "Inception", "Album", "2010-07-13", secondary=["Soundtrack"])]
    assert pick_album(releases) == ("ost", "Inception")


def test_the_songs_own_single_beats_a_more_released_other_single():
    search = {"recordings": [_search_hit("Lose Yourself", "Eminem", [
        _release("just", "Just Lose It", "Single", "2004-10-01"),
        _release("just", "Just Lose It", "Single", "2004-10-02"),
        _release("just", "Just Lose It", "Single", "2004-10-03"),
        _release("own", "Lose Yourself", "Single", "2002-10-28"),
    ])]}
    assert album_from_search(search, "Lose Yourself", "Eminem") == ("own", "Lose Yourself")


def test_recording_album_ignores_releases_of_other_artists(monkeypatch):
    from src.metadata import musicbrainz

    rec = {"title": "One Kiss", "artist-credit": [_credit("Calvin Harris", ", "), _credit("Dua Lipa")], "releases": [
        _credited_release("dua", "Dua Lipa", "Album", "2018-10-19", "Dua Lipa"),
        _credited_release("single", "One Kiss", "Single", "2018-04-06", "Calvin Harris"),
    ]}
    monkeypatch.setattr(musicbrainz, "_mb_json_get", lambda path, params: rec if path.startswith("recording/") else {})
    assert musicbrainz._get_recording_data("rec-7")["album_mbid"] == "single"
