"""The live LLM: Google Gemini behind the call store (U1, U3, U4, U8, U10), scored by U9's checks.

Replies replay with the measured latency and cost of the original call. A call that still fails
after the SDK's retry raises ProviderFailure, which fails the node. A reply with no text (a blocked
prompt, or max_tokens spent on thinking) was still paid for, so it is stored and then fails the
node every time, the same for every team. Logs and errors never hold message text.
"""

import time
from functools import partial
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from app.config import LLM_MODELS, LLM_PRICES_PER_1K_USD
from app.providers.base import (CallMeasure, JevProvider, LLMReply, LLMRequest, ProviderCall,
                                ProviderFailure)
from app.providers.call_store import CallStore, Fetched, SpendCapReached
from app.providers.factory import close_provider
from app.providers.llm_wording import system_prompt
from app.providers.reply_checks import check_reply

PROVIDER = "gemini"
TIMEOUT_MS = 20_000  # per attempt (U10)
RETRY = types.HttpRetryOptions(attempts=2)  # two attempts with backoff (U10)
# As low as each model allows (U8): gemini-4-argon has no minimal.
THINKING_LEVEL = {"small": "MINIMAL", "large": "LOW"}


def build_request(request: LLMRequest) -> dict[str, Any]:
    """The exact request fields, which are also the call store's key."""
    return {"system": system_prompt(request.prompt, request.context), "user": request.text,
            "max_tokens": request.max_tokens, "thinking_level": THINKING_LEVEL[request.model]}


def _failure(error: Exception, latency_ms: float) -> ProviderFailure:
    match error:
        case errors.APIError(code=429):
            return ProviderFailure("rate_limited", "Gemini rate limit reached", retryable=True,
                                   latency_ms=latency_ms)
        case errors.APIError():
            # The status only: the body may quote the request.
            return ProviderFailure("provider_error", f"Gemini answered HTTP {error.code}",
                                   retryable=error.code >= 500, latency_ms=latency_ms)
        case httpx.TimeoutException() | TimeoutError():
            return ProviderFailure("timeout", "Gemini timed out", retryable=True,
                                   latency_ms=latency_ms)
        case _:
            return ProviderFailure("provider_error", "could not reach Gemini", retryable=True,
                                   latency_ms=latency_ms)


class GeminiLLMProvider:
    """Lives for one run, on that run's event loop: compute() builds it there and closes it."""

    name = PROVIDER

    def __init__(self, store: CallStore, api_key: str, judge: JevProvider, *,
                 client_args: dict[str, Any] | None = None,
                 retry: types.HttpRetryOptions = RETRY) -> None:
        self._store = store
        self._api_key = api_key
        self._judge = judge
        self._client_args = client_args
        self._retry = retry
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        # Made on the first real call, so a run that only replays opens no connection.
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key, http_options=types.HttpOptions(
                timeout=TIMEOUT_MS, retry_options=self._retry,
                async_client_args=self._client_args))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.aio.aclose()
        await close_provider(self._judge)

    async def _fetch(self, tier: str, request: dict[str, Any]) -> Fetched:
        started = time.perf_counter()
        config = types.GenerateContentConfig(
            system_instruction=request["system"], max_output_tokens=request["max_tokens"],
            thinking_config=types.ThinkingConfig(thinking_level=request["thinking_level"]))
        try:
            response = await self._get_client().aio.models.generate_content(
                model=LLM_MODELS[PROVIDER][tier], contents=request["user"], config=config)
        except (errors.APIError, httpx.HTTPError, TimeoutError, OSError) as error:
            raise _failure(error, (time.perf_counter() - started) * 1000) from error
        usage = response.usage_metadata
        tokens_in = (usage.prompt_token_count or 0) if usage else 0
        # Thinking tokens count toward the limit and bill as output (U8).
        tokens_out = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                      if usage else 0)
        prices = LLM_PRICES_PER_1K_USD[PROVIDER][tier]
        finish = response.candidates[0].finish_reason if response.candidates else None
        feedback = response.prompt_feedback
        blocked = feedback.block_reason if feedback else None
        reason = f"prompt blocked: {blocked.value}" if blocked else finish.value if finish else None
        return Fetched(response={"text": response.text or "", "no_text_reason": reason},
                       tokens_in=tokens_in, tokens_out=tokens_out,
                       cost_usd=(tokens_in * prices["in"] + tokens_out * prices["out"]) / 1000)

    async def generate(self, request: LLMRequest, call: ProviderCall) -> LLMReply:
        fields = build_request(request)
        try:
            stored = await self._store.call(PROVIDER, LLM_MODELS[PROVIDER][request.model], fields,
                                            partial(self._fetch, request.model, fields))
            text = stored.response["text"]
            if not text.strip():
                raise ProviderFailure(
                    "provider_error",
                    f"Gemini returned no text ({stored.response['no_text_reason']})",
                    retryable=False, latency_ms=stored.latency_ms)
            check = await check_reply(text, request, call, self._judge)
        except SpendCapReached as error:
            raise ProviderFailure("spend_cap", str(error), retryable=False) from error
        return LLMReply(
            text=text, tokens_in=stored.tokens_in, tokens_out=stored.tokens_out, taint=check.taint,
            verdicts=check.verdicts,
            measure=CallMeasure(latency_ms=stored.latency_ms, cost_usd=stored.cost_usd,
                                tokens_in=stored.tokens_in, tokens_out=stored.tokens_out,
                                replayed=stored.replayed))
