from types import SimpleNamespace

from src.analysis.similarity import SimilarityIndex


def _song(song_id: str, value: float) -> SimpleNamespace:
    features = SimpleNamespace(bpm=value, happy=value, arousal=value)
    return SimpleNamespace(id=song_id, dsp_features=features, ml_moods=features, ml_profile=features)


class _Library:
    """Counts how often the (expensive) full library load happens."""

    def __init__(self, songs: list[SimpleNamespace]) -> None:
        self.songs = songs
        self.loads = 0

    def load(self) -> list[SimpleNamespace]:
        self.loads += 1
        return self.songs


def test_neighbors_are_closest_first() -> None:
    library = _Library([_song("a", 1.0), _song("b", 2.0), _song("c", 10.0)])

    neighbors = SimilarityIndex().neighbors_for("a", 3, library.load)

    assert neighbors == ["b", "c"]


def test_library_is_loaded_once_while_the_song_count_is_unchanged() -> None:
    library = _Library([_song("a", 1.0), _song("b", 2.0), _song("c", 10.0)])
    index = SimilarityIndex()

    index.neighbors_for("a", 3, library.load)
    index.neighbors_for("c", 3, library.load)

    assert library.loads == 1


def test_index_is_rebuilt_when_a_song_was_added() -> None:
    library = _Library([_song("a", 1.0), _song("b", 2.0), _song("c", 10.0)])
    index = SimilarityIndex()
    index.neighbors_for("a", 3, library.load)

    library.songs.append(_song("d", 1.1))
    neighbors = index.neighbors_for("a", 4, library.load)

    assert library.loads == 2
    assert neighbors[0] == "d"
