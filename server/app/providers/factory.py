"""The providers a run uses, from settings (U2): the mocks unless JEV_MODE / LLM_MODE say live.

Live Claude isn't built; Settings.live_problems() stops the server from starting with it. The
Gemini module is imported only when used: its SDK is heavy and most processes run on mocks.
"""

from functools import partial
from typing import Any

from app.config import Settings, get_settings
from app.db.session import session_scope
from app.providers.base import JevProvider, LLMProvider
from app.providers.call_store import CallStore
from app.providers.mock_jev import MockJevProvider
from app.providers.mock_llm import MockLLMProvider
from app.providers.typesafe_jev import TypeSafeJevProvider


def call_store_for(app: Any) -> CallStore:
    """One store per app, so runs computing at the same time share identical in-flight calls."""
    store = getattr(app.state, "call_store", None)
    if store is None:
        store = CallStore(partial(session_scope, app), get_settings().live_spend_cap_usd)
        app.state.call_store = store
    return store


def jev_provider(settings: Settings, store: CallStore | None = None) -> JevProvider:
    if settings.jev_mode != "live":
        return MockJevProvider()
    if store is None or not settings.typesafe_api_key:
        raise ValueError("live Jev needs a call store and TYPESAFE_API_KEY")
    return TypeSafeJevProvider(store, settings.typesafe_api_key)


def llm_provider(settings: Settings, store: CallStore | None = None) -> LLMProvider:
    if settings.llm_mode != "live":
        return MockLLMProvider(name=settings.llm_provider)
    if settings.llm_provider != "gemini":
        raise NotImplementedError(f"the live {settings.llm_provider} provider isn't built")
    if store is None or not settings.gemini_api_key or not settings.typesafe_api_key:
        raise ValueError("live Gemini needs a call store, GEMINI_API_KEY and TYPESAFE_API_KEY")
    from app.providers.gemini_llm import GeminiLLMProvider
    # Its own judge, in every JEV_MODE: the scoring must not depend on the mock router's mode.
    judge = TypeSafeJevProvider(store, settings.typesafe_api_key)
    return GeminiLLMProvider(store, settings.gemini_api_key, judge)


async def close_provider(provider: object) -> None:
    """Release what a provider holds; the mocks hold nothing."""
    if (aclose := getattr(provider, "aclose", None)) is not None:
        await aclose()
