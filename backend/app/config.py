from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # Database
    database_url: str = "sqlite:///./test.db"
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "mydb"
    database_user: str = "myuser"
    database_password: str = "mypassword"

    # App
    app_env: str = "development"
    secret_key: str = "change-me-in-production"
    debug: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
