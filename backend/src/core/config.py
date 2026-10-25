import logging
import sys
from pathlib import Path

from pydantic_settings import BaseSettings

# backend/ directory — anchor for all default paths so they work regardless of cwd
logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".m4a"}


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/music_recommender"
    debug: bool = False
    model_cache_dir: Path = Path("model_cache")
    audio_process_models_dir: Path = Path("src/audio_process/Models")
    datasets_dir: Path = _BACKEND_DIR / "datasets"
    short_audio_dir: Path = _BACKEND_DIR / "short_audio"
    lastfm_api_key: str = ""
    acoustid_api_key: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    # Site login (prod only). Hash: `python -m src.auth.hash_password`;
    # secret: any long random string. Both empty = nobody can log in.
    site_password_hash: str = ""
    session_secret: str = ""
    session_days: int = 30
    session_cookie_secure: bool = True
    # Personal accounts (optional): login cookie lifetime and reset-mail links.
    user_session_days: int = 90
    public_base_url: str = "http://127.0.0.1:5173"
    # Brevo transactional mail; both empty = reset links are only logged.
    brevo_api_key: str = ""
    mail_from: str = ""
    mail_from_name: str = "Music Recommender"
    # Must match a redirect URI of the Spotify app exactly.
    spotify_redirect_uri: str = "http://127.0.0.1:5173/api/spotify/callback"

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


_LOCAL_URL_PREFIXES = ("http://127.0.0.1", "http://localhost")


def warn_local_urls(s: "Settings | None" = None) -> None:
    """Warn when production (secure cookies) still uses the local default URLs.

    Reset mails would then link to 127.0.0.1 and Spotify would refuse the callback.
    """
    s = s or settings
    if not s.session_cookie_secure:
        return
    for value, env in ((s.public_base_url, "PUBLIC_BASE_URL"), (s.spotify_redirect_uri, "SPOTIFY_REDIRECT_URI")):
        if value.startswith(_LOCAL_URL_PREFIXES):
            logger.warning("[Config] %s is %s; set the public https address in .env.prod", env, value)


settings = Settings()
