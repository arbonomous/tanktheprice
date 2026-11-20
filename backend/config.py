"""Backend runtime settings loaded from .env.local and process environment."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_LOCAL = ROOT_DIR / ".env.local"
if ENV_LOCAL.exists():
    load_dotenv(ENV_LOCAL, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_LOCAL), env_file_encoding="utf-8", extra="ignore")

    feed_mode: Literal["auto", "live", "simulator"] = "auto"
    straits_live_api_key: str = ""
    datalastic_api_key: str = ""
    marinetraffic_api_key: str = ""
    alphavantage_api_key: str = ""

    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'hormuzflow.db'}"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    refresh_interval_seconds: int = 300


settings = Settings()
