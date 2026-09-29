from src.metadata.musicbrainz import RecordingIdentity, pick_album, recording_identity


def _release(rg_id: str, title: str, rg_type: str, date: str | None, status: str = "Official") -> dict:
    return {"title": title, "date": date, "status": status,
            "release-group": {"id": rg_id, "title": title, "primary-type": rg_type}}


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
