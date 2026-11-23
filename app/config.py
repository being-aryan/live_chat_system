from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Live Chat System"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    DATABASE_URL: str
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=1, le=120)
    DB_POOL_RECYCLE: int = Field(default=1800, ge=60)

    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1)

    REDIS_URL: str = "redis://localhost:6379/0"
    ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:8501", "http://127.0.0.1:8501"]
    )

    RATE_LIMIT_LOGIN: int = Field(default=5, ge=1)
    RATE_LIMIT_REGISTER: int = Field(default=5, ge=1)
    RATE_LIMIT_REFRESH: int = Field(default=10, ge=1)
    RATE_LIMIT_TICKET: int = Field(default=20, ge=1)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1)
    WEBSOCKET_MAX_MESSAGES_PER_SECOND: int = Field(default=10, ge=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use PostgreSQL with asyncpg")
        return value

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_allowed_origins(cls, value: list[str]) -> list[str]:
        origins = [origin.rstrip("/") for origin in value if origin.strip()]
        if not origins or "*" in origins:
            raise ValueError(
                "ALLOWED_ORIGINS must contain explicit origins and cannot use '*'"
            )
        return list(dict.fromkeys(origins))

    @field_validator("DEBUG")
    @classmethod
    def disable_debug_in_production(cls, value: bool, info) -> bool:
        if value and info.data.get("ENVIRONMENT") == "production":
            raise ValueError("DEBUG must be disabled in production")
        return value


settings = Settings()
