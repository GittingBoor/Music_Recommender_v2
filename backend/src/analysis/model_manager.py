import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from src.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://essentia.upf.edu/models"


@dataclass(frozen=True)
class ModelSpec:
    key: str
    relative_url: str
    description: str

    @property
    def filename(self) -> str:
        return self.relative_url.split("/")[-1]

    @property
    def download_url(self) -> str:
        return f"{BASE_URL}/{self.relative_url}"


MODELS: list[ModelSpec] = [
    # --- Embeddings ---
    ModelSpec(
        key="effnet_embedding",
        relative_url="feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb",
        description="Discogs-EffNet (primary embedding for all EffNet classifiers)",
    ),
    ModelSpec(
        key="musicnn_embedding",
        relative_url="feature-extractors/musicnn/msd-musicnn-1.pb",
        description="MSD-MusiCNN (embedding for Arousal/Valence DEAM model)",
    ),
    # --- Mood ---
    ModelSpec(
        key="mood_happy",
        relative_url="classification-heads/mood_happy/mood_happy-discogs-effnet-1.pb",
        description="Happy vs. not happy",
    ),
    ModelSpec(
        key="mood_sad",
        relative_url="classification-heads/mood_sad/mood_sad-discogs-effnet-1.pb",
        description="Sad vs. not sad",
    ),
    ModelSpec(
        key="mood_aggressive",
        relative_url="classification-heads/mood_aggressive/mood_aggressive-discogs-effnet-1.pb",
        description="Aggressive vs. not aggressive",
    ),
    ModelSpec(
        key="mood_party",
        relative_url="classification-heads/mood_party/mood_party-discogs-effnet-1.pb",
        description="Party / energetic vs. not",
    ),
    ModelSpec(
        key="mood_relaxed",
        relative_url="classification-heads/mood_relaxed/mood_relaxed-discogs-effnet-1.pb",
        description="Relaxed vs. not relaxed",
    ),
    ModelSpec(
        key="mood_acoustic",
        relative_url="classification-heads/mood_acoustic/mood_acoustic-discogs-effnet-1.pb",
        description="Acoustic vs. non-acoustic",
    ),
    ModelSpec(
        key="mood_electronic",
        relative_url="classification-heads/mood_electronic/mood_electronic-discogs-effnet-1.pb",
        description="Electronic vs. non-electronic",
    ),
    # --- Arousal / Valence ---
    ModelSpec(
        key="arousal_valence",
        relative_url="classification-heads/deam/deam-msd-musicnn-2.pb",
        description="Arousal + Valence on 1–9 scale (DEAM dataset, requires MusiCNN embedding)",
    ),
    # --- Genre ---
    ModelSpec(
        key="genre_discogs400",
        relative_url="classification-heads/genre_discogs400/genre_discogs400-discogs-effnet-1.pb",
        description="400 Discogs music styles across 14 categories (multi-label)",
    ),
    # --- Approachability & Engagement ---
    ModelSpec(
        key="approachability",
        relative_url="classification-heads/approachability/approachability_2c-discogs-effnet-1.pb",
        description="Mainstream vs. niche appeal (2-class)",
    ),
    ModelSpec(
        key="engagement",
        relative_url="classification-heads/engagement/engagement_2c-discogs-effnet-1.pb",
        description="Active listening vs. background music (2-class)",
    ),
    # --- Instruments ---
    ModelSpec(
        key="instrument",
        relative_url="classification-heads/mtg_jamendo_instrument/mtg_jamendo_instrument-discogs-effnet-1.pb",
        description="40 instrument classes (multi-label)",
    ),
    # --- Voice ---
    ModelSpec(
        key="voice_instrumental",
        relative_url="classification-heads/voice_instrumental/voice_instrumental-discogs-effnet-1.pb",
        description="Vocal vs. instrumental",
    ),
    ModelSpec(
        key="gender",
        relative_url="classification-heads/gender/gender-discogs-effnet-1.pb",
        description="Voice gender (male vs. female dominant)",
    ),
]

_MODEL_INDEX: dict[str, ModelSpec] = {m.key: m for m in MODELS}


class ModelManager:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or settings.model_cache_dir

    def get_path(self, key: str) -> Path:
        if key not in _MODEL_INDEX:
            raise KeyError(f"Unknown model key '{key}'. Available: {list(_MODEL_INDEX)}")
        return self._cache_dir / _MODEL_INDEX[key].filename

    def is_cached(self, key: str) -> bool:
        return self.get_path(key).exists()

    def ensure_key(self, key: str) -> None:
        """Download a single model if not already cached."""
        if self.is_cached(key):
            return
        spec = _MODEL_INDEX[key]
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[Model] Downloading %s — %s", spec.key, spec.description)
        self._download(spec.download_url, self._cache_dir / spec.filename)
        logger.info("[Model] Saved %s", spec.key)

    def ensure_all(self) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        missing = [m for m in MODELS if not self.is_cached(m.key)]

        if not missing:
            logger.info("All %d models already cached in %s", len(MODELS), self._cache_dir)
            return

        logger.info(
            "%d/%d models need to be downloaded into %s",
            len(missing),
            len(MODELS),
            self._cache_dir,
        )

        for i, spec in enumerate(missing, start=1):
            dest = self._cache_dir / spec.filename
            logger.info("[%d/%d] Downloading %s — %s", i, len(missing), spec.key, spec.description)
            self._download(spec.download_url, dest)
            logger.info("[%d/%d] Saved → %s", i, len(missing), dest)

        logger.info("All models ready.")

    def _download(self, url: str, dest: Path) -> None:
        tmp = dest.with_suffix(".tmp")
        try:
            def _progress(block_count: int, block_size: int, total_size: int) -> None:
                if total_size <= 0:
                    return
                downloaded = block_count * block_size
                pct = min(downloaded / total_size * 100, 100)
                print(f"\r  {pct:5.1f}%  ({downloaded // 1_048_576} / {total_size // 1_048_576} MB)", end="", flush=True)

            urllib.request.urlretrieve(url, tmp, reporthook=_progress)
            print()
            tmp.rename(dest)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise


_manager: ModelManager | None = None


def get_manager() -> ModelManager:
    global _manager
    if _manager is None:
        _manager = ModelManager()
    return _manager


# ---------------------------------------------------------------------------
# Essentia algorithm instance cache
# ---------------------------------------------------------------------------
# Essentia TensorflowPredict* / TempoCNN / MusicExtractor instances are
# stateless between compute() calls — they can be built once and reused
# across all songs in a batch, saving ~21 graph reloads per song.
_algo_cache: dict = {}


def get_cached_algo(cache_key: tuple, builder):
    """Return a cached Essentia algorithm instance, building it once if needed.

    Parameters
    ----------
    cache_key:
        A hashable tuple that uniquely identifies the algorithm configuration
        (e.g. model path + output layer).  If it doesn't exist yet, *builder*
        is called to create the instance, which is then stored and returned.
    builder:
        Zero-argument callable that constructs and returns the algorithm.
    """
    algo = _algo_cache.get(cache_key)
    if algo is None:
        algo = builder()
        _algo_cache[cache_key] = algo
    return algo


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    get_manager().ensure_all()
