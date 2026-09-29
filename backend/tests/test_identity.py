from src.metadata.acoustid_client import pick_recording, split_credits
from src.metadata.identity import (
    AcoustidMatch,
    IdentityHint,
    MetadataSource,
    SongIdentity,
    credit_composer,
    expected_artists,
    needs_composer_check,
    resolve_identity,
    split_composer_prefix,
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


def test_composer_surname_from_the_video_matches_the_full_name():
    orchestra = SongIdentity("Serenade no. 13", "Academy of St Martin in the Fields", MetadataSource.ACOUSTID, "rec-5")
    identity = credit_composer(orchestra, "Mozart", ["Wolfgang Amadeus Mozart"])
    assert identity.raw_artist == "Wolfgang Amadeus Mozart"
    assert identity.featured_artists == ("Academy of St Martin in the Fields",)


def test_typographic_quotes_are_stored_as_plain_ones():
    identity = resolve_identity(AcoustidMatch("rec-6", "Hips Don’t Lie", "Shakira"), None, "", "")
    assert identity is not None and identity.title == "Hips Don't Lie"


def test_the_main_artist_is_never_featured():
    match = AcoustidMatch("rec-8", "Air on a G String", "HAUSER", ("London Symphony Orchestra", "HAUSER"))
    identity = resolve_identity(match, None, "", "")
    assert identity is not None and identity.featured_artists == ("London Symphony Orchestra",)


def test_composer_check_also_uses_the_artist_mentioned_in_the_video_title():
    orchestra = SongIdentity("Swan Lake: Act 2", "Orchestre symphonique de Montréal", MetadataSource.ACOUSTID, "rec-9")
    hint = IdentityHint("Swan Lake", "Orchestre symphonique de Montréal", MetadataSource.YOUTUBE_TITLE,
                        mentioned_artist="Tchaikovsky")
    assert needs_composer_check(orchestra, hint)
    assert expected_artists(hint) == ["Orchestre symphonique de Montréal", "Tchaikovsky"]


def _credited_rec(title: str, sources: int, *artists: str) -> dict:
    return {"id": f"{title}-{sources}", "title": title, "sources": sources, "artists": [{"name": a} for a in artists]}


def test_recording_with_a_guest_the_video_never_mentions_loses():
    remix = _credited_rec("Believer", 50, "Imagine Dragons", "Lil Wayne")
    original = _credited_rec("Believer", 20, "Imagine Dragons")
    picked = pick_recording([remix, original], "Believer", "Imagine Dragons - Believer (Official Music Video)")
    assert picked is original


def test_guests_named_in_the_video_title_are_fine():
    feat = _credited_rec("Titanium", 50, "David Guetta", "Sia")
    solo = _credited_rec("Titanium", 20, "David Guetta")
    picked = pick_recording([solo, feat], "Titanium", "David Guetta - Titanium ft. Sia (Official Video)")
    assert picked is feat


def test_composer_written_into_the_performers_title_becomes_the_artist():
    rousseau = SongIdentity("Beethoven - Moonlight Sonata (1st Movement)", "Rousseau", MetadataSource.ACOUSTID, "rec-10")
    identity = split_composer_prefix(rousseau, ["Beethoven"])
    assert identity.raw_artist == "Beethoven"
    assert identity.title == "Moonlight Sonata (1st Movement)"
    assert identity.featured_artists == ("Rousseau",)


def test_a_title_starting_with_an_unnamed_artist_stays():
    song = SongIdentity("Hans Zimmer - Time", "Some Pianist", MetadataSource.ACOUSTID, "rec-11")
    assert split_composer_prefix(song, ["Some Pianist"]) == song
