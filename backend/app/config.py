"""The configuration for the backend application.

"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """The settings of the backend application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API keys
    RECALL_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # The SQLite file. Default is the path in the container
    DB_PATH: Path = Path("/app/data/recall_demo.sqlite3")

    # Browser origins that can call this API
    CORS_ORIGINS: list[str] = [
        "https://recall.samneet.com",  # The deployed Cloudflare Worker.
        "http://localhost:8787",  # wrangler dev, the default port.
        "http://127.0.0.1:8787",
    ]

    CORS_METHODS: list[str] = ["GET", "POST", "OPTIONS"]
    CORS_HEADERS: list[str] = ["Authorization", "Content-Type"]


settings = Settings()

# Aliases. `app/main.py` imports by these names
CORS_ORIGINS = settings.CORS_ORIGINS
CORS_METHODS = settings.CORS_METHODS
CORS_HEADERS = settings.CORS_HEADERS
