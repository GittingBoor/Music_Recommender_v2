from src.youtube.library_match import LibraryMatcher

LIBRARY = [
    ("Hey Brother", "Avicii"),
    ("Burn", "Ellie Goulding"),
    ("I Could Be the One (Nicktim radio edit)", "Avicii, Nicky Romero"),
    ("Summer Jam", "R.I.O., U‐Jean"),
    ("Talk Dirty", "Jason Derulo, 2 Chainz"),
    ("A media luz", "Ha*Ash"),
    (None, "Unknown"),
]


def _matcher() -> LibraryMatcher:
    return LibraryMatcher(LIBRARY)


def test_typical_video_title_matches():
    assert _matcher().contains("Avicii - Hey Brother (Official Video)", "AviciiOfficialVEVO")


def test_topic_channel_supplies_the_artist():
    assert _matcher().contains("Hey Brother", "Avicii - Topic")


def test_bracketed_version_suffix_is_ignored():
    assert _matcher().contains("Avicii vs Nicky Romero - I Could Be The One [Nicktim]", None)


def test_punctuation_in_names_is_normalised():
    assert _matcher().contains("R.I.O feat U-jean - Summer Jam (lyrics)", None)
    assert _matcher().contains("Ha-Ash - A Media Luz", None)


def test_featured_artist_alone_is_enough():
    assert _matcher().contains("2 Chainz & Jason Derulo — Talk Dirty", None)


def test_same_title_by_other_artist_does_not_match():
    assert not _matcher().contains("Usher - Burn", "UsherVEVO")


def test_title_must_be_a_whole_word():
    assert not _matcher().contains("Ellie Goulding - Burning Desire", None)


def test_unrelated_video_does_not_match():
    assert not _matcher().contains("Daft Punk - One More Time", "Daft Punk")
