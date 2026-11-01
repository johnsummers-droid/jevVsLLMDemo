"""Server settings.

Env-driven settings via pydantic-settings (read from the environment and server/.env;
.env.example lists every variable). Model ids and prices are constants (MVP step 2, T35): the
real providers' prices, which the mocks bill at too, so mock and live costs compare.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LLMProviderName = Literal["gemini", "claude"]
DEFAULT_LLM_PROVIDER: LLMProviderName = "gemini"

# Model id per provider and tier (plan1.txt MVP STEP 2, read 2026-10-31).
LLM_MODELS: dict[str, dict[str, str]] = {
    "gemini": {"small": "gemini-3.5-flash-lite", "large": "gemini-4-argon"},
    "claude": {"small": "claude-haiku-5-5", "large": "claude-sonnet-5-5"},
}

# USD per 1k tokens, per provider and tier. Output prices include thinking tokens. gemini-4-argon
# rises to $0.004 / $0.020 per 1k on 2026-12-01: update it if the workshop is after that.
LLM_PRICES_PER_1K_USD: dict[str, dict[str, dict[str, float]]] = {
    "gemini": {"small": {"in": 0.0003, "out": 0.0025}, "large": {"in": 0.002, "out": 0.010}},
    "claude": {"small": {"in": 0.0001, "out": 0.0005}, "large": {"in": 0.002, "out": 0.010}},
}

# Jev (TypeSafe System One). Pinned, not jev-latest: the router threshold is tuned against one
# version (U1). Input tokens only; output is free.
JEV_MODEL = "jev-1.14.0"
JEV_PRICE_PER_1K_INPUT_USD = 0.000042

ProviderMode = Literal["mock", "live"]
# Live providers that exist so far; live mode for anything else refuses to start (U2).
LIVE_JEV_AVAILABLE = True
LIVE_LLM_AVAILABLE: frozenset[str] = frozenset({"gemini"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    allowed_origin_regex: str | None = None
    # Secrets have no defaults: T12 refuses to create sessions or tokens while they are unset.
    facilitator_code: str | None = None
    token_secret: str | None = None
    log_level: str = "info"
    # Which LLM the answer generator uses (U1/U2): its prices in mock mode, its API in live mode.
    llm_provider: LLMProviderName = DEFAULT_LLM_PROVIDER
    # mock (default: tests, CI, headless) or live (real API calls through the call store, U2/U3).
    jev_mode: ProviderMode = "mock"
    llm_mode: ProviderMode = "mock"
    # Server-only API keys (U12). Empty means unset.
    typesafe_api_key: str | None = None
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    # Real (uncached) calls may spend at most this much per UTC day (U10).
    live_spend_cap_usd: float = Field(default=10, ge=0)
    # Real calls in flight per provider, across all runs (U5). Jev: 16 at ~0.2 s stays under the
    # org's 80 req/s. Gemini: raise it if the key's tier allows and official runs prepare slowly.
    live_jev_concurrency: int = Field(default=16, ge=1)
    live_llm_concurrency: int = Field(default=4, ge=1)

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

    @field_validator("allowed_origin_regex", "facilitator_code", "token_secret", "typesafe_api_key",
                     "gemini_api_key", "anthropic_api_key", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        return None if value == "" else value


    def llm_api_key(self) -> str | None:
        return self.gemini_api_key if self.llm_provider == "gemini" else self.anthropic_api_key

    def live_problems(self) -> list[str]:
        """Why live mode cannot run with these settings; empty when it can (or nothing is live)."""
        problems = []
        if self.jev_mode == "live":
            if not LIVE_JEV_AVAILABLE:
                problems.append("JEV_MODE=live: the live Jev provider is not built yet (T36)")
            if not self.typesafe_api_key:
                problems.append("JEV_MODE=live needs TYPESAFE_API_KEY")
        if self.llm_mode == "live":
            if self.llm_provider not in LIVE_LLM_AVAILABLE:
                problems.append(f"LLM_MODE=live: the live {self.llm_provider} provider is not "
                                "built yet")
            if not self.llm_api_key():
                key = "GEMINI_API_KEY" if self.llm_provider == "gemini" else "ANTHROPIC_API_KEY"
                problems.append(f"LLM_MODE=live with LLM_PROVIDER={self.llm_provider} needs {key}")
            if not self.typesafe_api_key:
                problems.append("LLM_MODE=live needs TYPESAFE_API_KEY: Jev judges the real replies")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
