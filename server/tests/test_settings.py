import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATABASE_URL", "ALLOWED_ORIGINS", "ALLOWED_ORIGIN_REGEX", "FACILITATOR_CODE", "TOKEN_SECRET", "LLM_PROVIDER", "JEV_MODE", "LLM_MODE",
                 "TYPESAFE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "LIVE_SPEND_CAP_USD"):
        monkeypatch.delenv(name, raising=False)


def load() -> Settings:
    return Settings(_env_file=None)


def test_defaults() -> None:
    settings = load()
    assert settings.database_url == "sqlite:///./dev.db"
    assert settings.allowed_origins == ["http://localhost:5173"]
    assert settings.allowed_origin_regex is None
    assert settings.facilitator_code is None and settings.token_secret is None
    assert settings.llm_provider == "gemini"


def test_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    assert load().llm_provider == "claude"
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(ValueError):
        load()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("sqlite:///./other.db", "sqlite:///./other.db"),
    ],
)
def test_database_url_rewrite(monkeypatch: pytest.MonkeyPatch, url: str, expected: str) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    assert load().database_url == expected


def test_allowed_origins_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://a.example , https://b.example,,")
    assert load().allowed_origins == ["https://a.example", "https://b.example"]


def test_empty_values_are_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ALLOWED_ORIGIN_REGEX", "FACILITATOR_CODE", "TOKEN_SECRET"):
        monkeypatch.setenv(name, "")
    settings = load()
    assert settings.allowed_origin_regex is None
    assert settings.facilitator_code is None and settings.token_secret is None


def test_live_defaults_are_mock_and_safe() -> None:
    settings = load()
    assert (settings.jev_mode, settings.llm_mode) == ("mock", "mock")
    assert settings.live_spend_cap_usd == 10
    assert settings.typesafe_api_key is None and settings.gemini_api_key is None
    assert settings.live_problems() == []


def test_empty_keys_are_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert load().gemini_api_key is None


def test_live_mode_needs_its_key_and_its_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_MODE", "live")
    monkeypatch.setenv("LLM_MODE", "live")
    problems = " | ".join(load().live_problems())
    assert "TYPESAFE_API_KEY" in problems and "GEMINI_API_KEY" in problems
    assert "not built" not in problems
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert "Jev judges" in " | ".join(load().live_problems())  # the judge needs TypeSafe (U9)
    monkeypatch.setenv("TYPESAFE_API_KEY", "t")
    assert load().live_problems() == []
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    problems = " | ".join(load().live_problems())
    assert "ANTHROPIC_API_KEY" in problems and "not built" in problems


def test_live_mode_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import app

    app.dependency_overrides.clear()
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("LLM_PROVIDER", "claude")  # not built, whatever keys server/.env holds
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="cannot start in live mode"), TestClient(app):
            pass
    finally:
        get_settings.cache_clear()


def test_every_provider_and_tier_has_a_model_and_prices() -> None:
    from app.catalog.definitions.llm import LLM_ANSWER_GENERATOR
    from app.config import LLM_MODELS, LLM_PRICES_PER_1K_USD

    tiers = next(p for p in LLM_ANSWER_GENERATOR.params if p.key == "model").options
    for provider in ("gemini", "claude"):
        assert set(LLM_MODELS[provider]) == set(tiers)
        for tier in tiers:
            prices = LLM_PRICES_PER_1K_USD[provider][tier]
            assert 0 < prices["in"] < prices["out"]


def test_the_factory_builds_mocks_billed_as_the_configured_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.providers.factory import jev_provider, llm_provider
    from app.providers.mock_jev import MockJevProvider

    monkeypatch.setenv("LLM_PROVIDER", "claude")
    settings = load()
    assert isinstance(jev_provider(settings), MockJevProvider)
    assert llm_provider(settings).name == "claude"


def test_the_factory_builds_live_jev_only_with_a_store_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.providers.call_store import CallStore
    from app.providers.factory import jev_provider
    from app.providers.typesafe_jev import TypeSafeJevProvider

    monkeypatch.setenv("JEV_MODE", "live")
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        jev_provider(load(), CallStore(lambda: None, 1))
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    assert load().live_problems() == []
    with pytest.raises(ValueError, match="call store"):
        jev_provider(load())
    built = jev_provider(load(), CallStore(lambda: None, 1))
    assert isinstance(built._live, TypeSafeJevProvider)
