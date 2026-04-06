from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    app_env: str
    database_url: str
    cors_origins: list[str]
    aws_region: str
    agentcore_timeout_seconds: int
    incident_daddy_runtime_arn: str
    bug_daddy_runtime_arn: str
    reviewer_daddy_runtime_arn: str
    sme_agent_runtime_arn: str

    @property
    def using_mysql(self) -> bool:
        return self.database_url.startswith("mysql")


@lru_cache
def get_settings() -> Settings:
    default_sqlite = "sqlite:///./platform.db"
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL", default_sqlite),
        cors_origins=_list("CORS_ORIGINS", ["http://localhost:3000"]),
        aws_region=os.getenv("AWS_REGION", "ap-south-1"),
        agentcore_timeout_seconds=int(os.getenv("AGENTCORE_TIMEOUT_SECONDS", "30")),
        incident_daddy_runtime_arn=os.getenv("INCIDENT_DADDY_RUNTIME_ARN", ""),
        bug_daddy_runtime_arn=os.getenv("BUG_DADDY_RUNTIME_ARN", ""),
        reviewer_daddy_runtime_arn=os.getenv("REVIEWER_DADDY_RUNTIME_ARN", ""),
        sme_agent_runtime_arn=os.getenv("SME_AGENT_RUNTIME_ARN", ""),
    )
