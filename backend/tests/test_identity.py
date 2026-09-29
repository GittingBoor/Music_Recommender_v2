from src.metadata.acoustid_client import pick_recording, split_credits
from src.metadata.identity import (
    AcoustidMatch,
    IdentityHint,
    MetadataSource,
    SongIdentity,
    credit_composer,
    needs_composer_check,
    resolve_identity,
)

_NO_MATCH = AcoustidMatch(None, None, None)
_HINT = IdentityHint(title="Hello", artist="Adele", source=MetadataSource.YOUTUBE_TITLE)


def test_acoustid_wins_over_hint_and_tags():
    identity = resolve_identity(AcoustidMatch("rec-1", "Hey Brother", "Avicii"), _HINT, "Tag Title", "Tag Artist")
    assert identity == SongIdentity("Hey Brother", "Avicii", MetadataSource.ACOUSTID, "rec-1")


def test_acoustid_featured_artists_are_kept_apart_from_the_artist():
    match = AcoustidMatch("rec-2", "Get Lucky", "Daft Punk", ("Pharrell Williams", "Nile Rodgers"))
    identity = resolve_identity(match, None, "", "")
    assert identity is not None
    assert identity.raw_artist == "Daft Punk"
    assert identity.featured_artists == ("Pharrell Williams", "Nile Rodgers")


def test_hint_is_used_without_acoustid_and_leaves_recording_empty():
    identity = resolve_identity(_NO_MATCH, _HINT, "Tag Title", "Tag Artist")
    assert identity == SongIdentity("Hello", "Adele", MetadataSource.YOUTUBE_TITLE, None)


def test_file_tags_are_the_last_resort():
    identity = resolve_identity(_NO_MATCH, None, " Burn ", "Ellie Goulding")
    assert identity == SongIdentity("Burn", "Ellie Goulding", MetadataSource.FILE_TAGS, None)


def test_nothing_known_returns_none():
    assert resolve_identity(_NO_MATCH, None, "Only Title", "") is None
    assert resolve_identity(AcoustidMatch(None, "Title", None), None, "", "") is None


def test_split_credits_first_artist_is_main_the_rest_featured():
    credits = [{"id": "1", "name": "Dr. Dre"}, {"id": "2", "name": "Snoop Dogg", "joinphrase": ""}]
    assert split_credits(credits) == ("Dr. Dre", ("Snoop Dogg",))


def test_split_credits_keeps_band_names_with_ampersand_whole():
    assert split_credits([{"name": "Bob Marley & The Wailers"}]) == ("Bob Marley & The Wailers", ())
    assert split_credits(["Earth, Wind & Fire"]) == ("Earth, Wind & Fire", ())


def test_split_credits_without_artists():
    assert split_credits([]) == (None, ())


def _rec(title: str, sources: int) -> dict:
    return {"id": title, "title": title, "sources": sources}


def test_recording_matching_the_known_title_beats_more_sources():
    recordings = [_rec("Still Dre", 40), _rec("Still D.R.E.", 12)]
    assert pick_recording(recordings, "Still D.R.E.")["title"] == "Still D.R.E."


def test_most_sources_win_without_a_matching_title():
    recordings = [_rec("Still Dre", 40), _rec("Still D.R.E.", 12)]
    assert pick_recording(recordings, None)["title"] == "Still Dre"
    assert pick_recording(recordings, "Something Else")["title"] == "Still Dre"


def test_title_match_ignores_case_and_punctuation():
    recordings = [_rec("Smells Like Teen Spirit (live)", 50), _rec("Smells Like Teen Spirit", 5)]
    assert pick_recording(recordings, "smells like teen spirit")["title"] == "Smells Like Teen Spirit"


def test_version_markers_are_dropped_from_the_stored_title():
    match = AcoustidMatch("rec-3", "Remmidemmi (Yippie Yippie Yeah) (single-edit)", "Deichkind")
    identity = resolve_identity(match, None, "", "")
    assert identity is not None and identity.title == "Remmidemmi (Yippie Yippie Yeah)"
    tagged = resolve_identity(_NO_MATCH, None, "Wake Me Up (Radio Edit)", "Avicii")
    assert tagged is not None and tagged.title == "Wake Me Up"


_PERFORMANCE = SongIdentity("Gymnopédie no. 1", "Patrick Cohen", MetadataSource.ACOUSTID, "rec-4")


def test_composer_named_by_the_video_becomes_the_artist():
    identity = credit_composer(_PERFORMANCE, "Erik Satie", ["Erik Satie"])
    assert identity.raw_artist == "Erik Satie"
    assert identity.featured_artists == ("Patrick Cohen",)
    assert identity.title == "Gymnopédie no. 1" and identity.acoustid_id == "rec-4"


def test_performer_stays_when_the_video_names_someone_else():
    assert credit_composer(_PERFORMANCE, "Random Uploader", ["Erik Satie"]) == _PERFORMANCE


def test_composer_check_only_when_the_video_names_another_artist():
    assert needs_composer_check(_PERFORMANCE, IdentityHint("Gymnopédie No. 1", "Erik Satie", MetadataSource.YOUTUBE_TITLE))
    assert not needs_composer_check(_PERFORMANCE, IdentityHint("x", "patrick cohen", MetadataSource.YOUTUBE_TITLE))
    assert not needs_composer_check(_PERFORMANCE, None)
