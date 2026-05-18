from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/music_recommender"
    debug: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
