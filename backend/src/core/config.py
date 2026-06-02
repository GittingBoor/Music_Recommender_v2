import sys
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/music_recommender"
    debug: bool = False
    model_cache_dir: Path = Path("model_cache")
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


def _check_required_keys(s: Settings) -> None:
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
_check_required_keys(settings)
