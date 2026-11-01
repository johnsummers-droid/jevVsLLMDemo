"""The daily spend cap's fallback (U10): at the cap a run answers from the mocks and says so.

Stored replies keep replaying at the cap; only requests that would need a new real call fall back.
The warning reaches the team and the facilitator on run_started.
"""

from app.providers.base import (JevAnswer, JevProvider, JevQuestion, LLMProvider, LLMReply, LLMRequest,
                                ProviderCall, ProviderFailure)

WARNING = ("Today's AI spend limit was reached, so some answers in this run are simulated. "
           "Its numbers can't be compared with a fully live run.")


class _Fallback:
    def __init__(self, live: object) -> None:
        self._live = live
        self.warnings: list[str] = []

    def _fell_back(self, failure: ProviderFailure) -> None:
        if failure.code != "spend_cap":
            raise failure
        self.warnings = [WARNING]

    async def aclose(self) -> None:
        await self._live.aclose()


class JevWithFallback(_Fallback):
    def __init__(self, live: JevProvider, mock: JevProvider) -> None:
        super().__init__(live)
        self._mock = mock

    async def ask(self, state: str, questions: list[JevQuestion],
                  call: ProviderCall) -> list[JevAnswer]:
        try:
            return await self._live.ask(state, questions, call)
        except ProviderFailure as failure:
            self._fell_back(failure)
        return await self._mock.ask(state, questions, call)


class LLMWithFallback(_Fallback):
    def __init__(self, live: LLMProvider, mock: LLMProvider) -> None:
        super().__init__(live)
        self._mock = mock
        self.name = live.name

    async def generate(self, request: LLMRequest, call: ProviderCall) -> LLMReply:
        try:
            return await self._live.generate(request, call)
        except ProviderFailure as failure:
            self._fell_back(failure)
        return await self._mock.generate(request, call)
