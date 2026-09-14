"""Nearest-neighbour lookup over the full audio feature space.

Deliberately independent of :mod:`src.analysis.umap_generator`'s fitted state:
that singleton is re-fitted whenever the UMAP view switches to custom axes, so
its neighbours can silently collapse onto two features. Recommendations must
not depend on what someone picked in another tab, so this module always uses
all features and keeps its own cache.
"""

import logging
import threading

import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from src.analysis.umap_generator import ALL_FEATURES, _build_feature_matrix

logger = logging.getLogger(__name__)

# How many neighbours to keep per song; the player only needs the closest few,
# but a short list lets it skip songs it has already played.
NEIGHBOR_COUNT = 10


class SimilarityIndex:
    """Process-wide nearest-neighbour index over all audio features.

    The index is rebuilt lazily whenever the library size changes, which is the
    only way songs enter or leave in this application.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._neighbors: dict[str, list[str]] = {}
        self._song_count = 0

    def neighbors_for(self, song_id: str, songs: list) -> list[str]:
        """Return the most similar song IDs, closest first.

        Args:
            song_id: The song to find neighbours for.
            songs: All songs, with dsp/mood/profile relations loaded.

        Returns:
            Neighbour IDs, or an empty list if the song or index is unavailable.
        """
        self._ensure_built(songs)
        with self._lock:
            return list(self._neighbors.get(song_id, []))

    def invalidate(self) -> None:
        """Drop the cached index (called when the library is cleared)."""
        with self._lock:
            self._neighbors.clear()
            self._song_count = 0

    # ── internals ──────────────────────────────────────────────────────────

    def _ensure_built(self, songs: list) -> None:
        with self._lock:
            if self._neighbors and self._song_count == len(songs):
                return

        if len(songs) < 2:
            with self._lock:
                self._neighbors = {}
                self._song_count = len(songs)
            return

        logger.info("[Similarity] Building index over %d songs", len(songs))
        matrix = _build_feature_matrix(songs, ALL_FEATURES)
        scaled = StandardScaler().fit_transform(matrix)

        k = min(NEIGHBOR_COUNT, len(songs) - 1)
        finder = NearestNeighbors(n_neighbors=k + 1).fit(scaled)
        _, indices = finder.kneighbors(scaled)

        song_ids = [s.id for s in songs]
        # Column 0 is the song itself — skip it.
        built = {
            song_ids[row]: [song_ids[col] for col in indices[row][1:]]
            for row in range(len(song_ids))
        }

        with self._lock:
            self._neighbors = built
            self._song_count = len(songs)

    @staticmethod
    def _unused() -> None:  # pragma: no cover - placeholder for symmetry
        return None


_index = SimilarityIndex()


def get_similarity_index() -> SimilarityIndex:
    """Return the process-wide similarity index."""
    return _index
