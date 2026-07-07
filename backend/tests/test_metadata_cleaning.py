import pytest

from src.metadata.cleaning import (
    clean_title,
    normalize_date,
    parse_featured_artists,
    split_artist_featuring,
)


class TestCleanTitle:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Levels (Official Video)", "Levels"),
            ("Grenade [HQ]", "Grenade"),
            ("Diamonds [Official Lyrics Video _ HD_HQ]", "Diamonds"),
            ("Balada Boa (2012)", "Balada Boa"),
            ("Paradise - Official Video", "Paradise"),
            ("Sonnentanz | Klangkarussell - Topic", "Sonnentanz"),
            ("Skyfall (Remastered 2015)", "Skyfall"),
        ],
    )
    def test_removes_noise(self, raw: str, expected: str):
        assert clean_title(raw) == expected

    def test_keeps_clean_titles_unchanged(self):
        assert clean_title("Somebody That I Used to Know") == "Somebody That I Used to Know"

    def test_keeps_meaningful_brackets(self):
        # Brackets that are not upload noise must survive.
        assert clean_title("Don't Stop (Color on the Walls)") == "Don't Stop (Color on the Walls)"


class TestNormalizeDate:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2012-05-01", "2012-05-01"),
            ("20120501", "2012-05-01"),
            ("2012", "2012"),
            ("1 May 2012", "2012-05-01"),
            ("2012/05/01", "2012-05-01"),
            ("released in 2012", "2012"),
            ("garbage", None),
            (None, None),
            ("", None),
        ],
    )
    def test_formats(self, raw: str | None, expected: str | None):
        assert normalize_date(raw) == expected


class TestFeaturedArtists:
    def test_paren_feat(self):
        assert parse_featured_artists("Strobo Pop (feat. Nena)") == ["Nena"]

    def test_multiple_artists_split(self):
        assert parse_featured_artists("Song (feat. A & B)") == ["A", "B"]

    def test_bare_feat_without_brackets(self):
        assert parse_featured_artists("Rain Over Me feat Marc Anthony") == ["Marc Anthony"]

    def test_no_feat(self):
        assert parse_featured_artists("Levels") == []

    def test_split_artist_featuring(self):
        assert split_artist_featuring("David Guetta Feat. Kid Cudi") == (
            "David Guetta",
            ["Kid Cudi"],
        )
        assert split_artist_featuring("Adele") == ("Adele", [])
