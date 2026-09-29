from src.metadata.identity import IdentityHint, MetadataSource, SongIdentity, resolve_identity

_NO_MATCH = (None, None, None)
_HINT = IdentityHint(title="Hello", artist="Adele", source=MetadataSource.YOUTUBE_TITLE)


def test_acoustid_wins_over_hint_and_tags():
    identity = resolve_identity(("rec-1", "Hey Brother", "Avicii"), _HINT, "Tag Title", "Tag Artist")
    assert identity == SongIdentity("Hey Brother", "Avicii", MetadataSource.ACOUSTID, "rec-1")


def test_hint_is_used_without_acoustid_and_leaves_recording_empty():
    identity = resolve_identity(_NO_MATCH, _HINT, "Tag Title", "Tag Artist")
    assert identity == SongIdentity("Hello", "Adele", MetadataSource.YOUTUBE_TITLE, None)


def test_file_tags_are_the_last_resort():
    identity = resolve_identity(_NO_MATCH, None, " Burn ", "Ellie Goulding")
    assert identity == SongIdentity("Burn", "Ellie Goulding", MetadataSource.FILE_TAGS, None)


def test_nothing_known_returns_none():
    assert resolve_identity(_NO_MATCH, None, "Only Title", "") is None
    assert resolve_identity((None, "Title", None), None, "", "") is None
