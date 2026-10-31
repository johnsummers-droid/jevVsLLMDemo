"""The providers a run uses, from settings (U2): the mocks unless JEV_MODE / LLM_MODE say live.

Live providers arrive in T36 (Jev) and T37 (Gemini); until then Settings.live_problems() stops
the server from starting in live mode, so these only ever build mocks.
"""

from app.config import Settings
from app.providers.base import JevProvider, LLMProvider
from app.providers.mock_jev import MockJevProvider
from app.providers.mock_llm import MockLLMProvider


def jev_provider(settings: Settings) -> JevProvider:
    if settings.jev_mode == "live":
        raise NotImplementedError("the live Jev provider arrives in T36")
    return MockJevProvider()


def llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_mode == "live":
        raise NotImplementedError(f"the live {settings.llm_provider} provider arrives in T37")
    return MockLLMProvider(name=settings.llm_provider)
