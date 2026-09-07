from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "get1agent Control Plane"
    app_version: str = "0.1.0"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8000

    aws_region: str = "us-east-1"

    # Local dev: password URL. Production EC2: IAM auth (no password).
    database_use_iam: bool = False
    database_url: str | None = None
    database_host: str | None = None
    database_port: int = 5432
    database_name: str = "get1agent"
    database_iam_user: str = "get1agent_app"
    db_echo: bool = False

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    auth0_domain: str | None = None
    auth0_audience: str | None = None

    @model_validator(mode="after")
    def validate_database_settings(self) -> "Settings":
        if self.database_use_iam:
            missing = [
                name
                for name, value in {
                    "DATABASE_HOST": self.database_host,
                    "DATABASE_NAME": self.database_name,
                    "DATABASE_IAM_USER": self.database_iam_user,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(
                    f"IAM database auth requires: {', '.join(missing)}",
                )
        elif not self.database_url:
            raise ValueError("Set DATABASE_URL for local password auth")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
