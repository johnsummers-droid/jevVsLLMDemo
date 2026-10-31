import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATABASE_URL", "ALLOWED_ORIGINS", "ALLOWED_ORIGIN_REGEX", "FACILITATOR_CODE", "TOKEN_SECRET", "LLM_PROVIDER"):
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
