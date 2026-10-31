"""Server settings.

Env-driven settings via pydantic-settings (read from the environment and server/.env;
.env.example lists every variable). LLM prices stay constants: placeholders tuned in T5 so the
default graph misses the cost budget.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# USD per 1k tokens, per LLM tier.
LLM_PRICES_PER_1K_USD: dict[str, dict[str, float]] = {
    "small": {"in": 0.001, "out": 0.005},
    "large": {"in": 0.003, "out": 0.015},
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    allowed_origin_regex: str | None = None
    # Secrets have no defaults: T12 refuses to create sessions or tokens while they are unset.
    facilitator_code: str | None = None
    token_secret: str | None = None
    log_level: str = "info"
    # Which real LLM the answer generator uses once live mode lands (plan1.txt MVP STEP 2, U1/U2).
    # Nodes still run on the mock providers; nothing reads this yet.
    llm_provider: Literal["gemini", "claude"] = "gemini"

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, url: str) -> str:
        # Railway and Render hand out postgres:// URLs; SQLAlchemy needs the driver named.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _comma_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("allowed_origin_regex", "facilitator_code", "token_secret", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
