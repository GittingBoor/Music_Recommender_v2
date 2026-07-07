from src.db.models.song import generate_song_id


def test_deterministic():
    assert generate_song_id("Levels", "Avicii") == generate_song_id("Levels", "Avicii")


def test_length_is_22():
    assert len(generate_song_id("Levels", "Avicii")) == 22
    assert len(generate_song_id("", "")) == 22


def test_case_and_whitespace_insensitive():
    assert generate_song_id("  Levels ", "AVICII") == generate_song_id("levels", "avicii")


def test_different_songs_differ():
    assert generate_song_id("Levels", "Avicii") != generate_song_id("Levels", "Adele")
    assert generate_song_id("Levels", "Avicii") != generate_song_id("Skyfall", "Avicii")


def test_title_artist_not_interchangeable():
    assert generate_song_id("a", "b") != generate_song_id("b", "a")
