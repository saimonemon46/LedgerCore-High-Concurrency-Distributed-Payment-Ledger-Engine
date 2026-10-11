"""Application configuration and environment settings for LedgerCore."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Automatically load .env from project root if present
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Strongly typed application configuration settings."""

    # Application
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    app_port: int = int(os.getenv("APP_PORT", "8000"))

    # PostgreSQL Database
    postgres_user: str = os.getenv("POSTGRES_USER", "ledger_user")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "ledger_secret")
    postgres_db: str = os.getenv("POSTGRES_DB", "ledger_core")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))

    # Database connection URL
    database_url: str = os.getenv(
        "DATABASE_URL",
        (
            f"postgresql+asyncpg://{os.getenv('POSTGRES_USER', 'ledger_user')}:"
            f"{os.getenv('POSTGRES_PASSWORD', 'ledger_secret')}@"
            f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.getenv('POSTGRES_DB', 'ledger_core')}"
        ),
    )

    # Redis Cache & Stores
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_url: str = os.getenv(
        "REDIS_URL",
        f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/0",
    )

    # Connection Pool Settings
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    db_pool_timeout: float = float(os.getenv("DB_POOL_TIMEOUT", "30.0"))


@lru_cache
def get_settings() -> Settings:
    """Provides cached singleton settings instance."""
    return Settings()
