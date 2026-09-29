from src.metadata.musicbrainz import (
    RecordingIdentity,
    album_from_search,
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
    black = [_release("black", "Metallica", "Album", f"20{y:02d}-01-01") for y in (21, 22, 23)]
    search = {"recordings": [
        _search_hit("Enter Sandman", "Metallica", [_release("tosox", "TosoX Episode 3", "Album", "2018")]),
        _search_hit("Enter Sandman", "Metallica", black),
    ]}
    assert album_from_search(search, "Enter Sandman", "Metallica") == ("black", "Metallica")
