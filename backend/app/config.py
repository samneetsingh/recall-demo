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

    # The intake engine. The model answers with a strict JSON schema
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT_SECONDS: float = 30.0

    # Text-to-speech settings
    OPENAI_TTS_MODEL: str = "gpt-4o-mini-tts"
    OPENAI_TTS_VOICE: str = "alloy"
    OPENAI_TTS_INSTRUCTIONS: str = (
        "Speak in a calm, clear and unhurried voice. You are a clinical triage assistant who speaks to a patient who has a headache."
    )

    # Voice mode: the length of silence that triggers the end of a turn
    VOICE_TURN_GAP_SECONDS: float = 2.5

    # The limit of questions in one intake. The engine applies it, not the model
    INTAKE_MAX_TURNS: int = 6

    # Recall.ai. The host is specific to the region of the API key
    RECALL_API_BASE: str = "https://us-west-2.recall.ai"
    RECALL_BOT_NAME: str = "Headache Assistant"
    RECALL_TIMEOUT_SECONDS: float = 30.0

    # The workspace verification secret, `whsec_...`. An empty value refuses every webhook request
    RECALL_WEBHOOK_SECRET: str = ""

    # The wait between the closing line and the leave.
    BOT_LEAVE_DELAY_SECONDS: float = 3.0

    # Where Recall reaches this backend. Makes the realtime endpoint URL
    PUBLIC_BASE_URL: str = "https://recall-api.ss-ubuntu-01.net"

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
