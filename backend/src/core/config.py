import sys
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/music_recommender"
    debug: bool = False
    model_cache_dir: Path = Path("model_cache")
    audio_process_models_dir: Path = Path("src/audio_process/Models")
    lastfm_api_key: str = ""
    acoustid_api_key: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    class Config:
        env_file = ".env"


_REQUIRED_KEYS: list[tuple[str, str]] = [
    ("lastfm_api_key",      "LASTFM_API_KEY"),
    ("acoustid_api_key",    "ACOUSTID_API_KEY"),
    ("spotify_client_id",   "SPOTIFY_CLIENT_ID"),
    ("spotify_client_secret", "SPOTIFY_CLIENT_SECRET"),
]


def check_required_keys(s: "Settings | None" = None) -> None:
    """Exit with a clear message if required API keys are missing.

    Called at application startup (FastAPI lifespan) and CLI start — never at
    import time, so modules stay importable without a .env (e.g. in tests).
    """
    s = s or settings
    missing = [env for attr, env in _REQUIRED_KEYS if not getattr(s, attr)]
    if not missing:
        return
    lines = "\n".join(f"  - {k}" for k in missing)
    print(
        f"\n[Config] FATAL — missing required API keys:\n{lines}\n"
        f"Set them in backend/.env and restart.\n",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(1)


settings = Settings()
