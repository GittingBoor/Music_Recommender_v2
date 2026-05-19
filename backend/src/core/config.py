from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/music_recommender"
    debug: bool = False
    model_cache_dir: Path = Path("model_cache")
    lastfm_api_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
