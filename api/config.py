"""Centralized settings loaded from environment / .env file."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Anthropic
    anthropic_api_key: str
    anthropic_model: str = "claude-opus-4-7"

    # SQL Server
    mssql_host: str = "localhost"
    mssql_port: int = 1433
    mssql_user: str = "sa"
    mssql_password: str
    mssql_database: str = "olist"

    # CORS
    allowed_origins: str = "http://localhost:3000,https://olist.show"


@lru_cache
def get_settings() -> Settings:
    return Settings()
