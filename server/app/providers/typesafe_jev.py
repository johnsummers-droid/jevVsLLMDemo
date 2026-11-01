"""The live Jev provider: TypeSafe's System One API behind the call store (U1, U3, U4, U7, U10).

Identical requests are answered once and replayed, with the measured latency and cost of the
original call. A call that still fails after the SDK's retry raises ProviderFailure, which fails
the node; there is no silent fallback to an answer. Logs and errors never hold message text.
"""

import time
from collections.abc import Callable
from functools import partial
from typing import Any

import httpx2
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    RetryPolicy,
    SystemOneResponse,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
    TypeSafeAPITimeoutError,
    TypeSafeError,
    TypeSafeRateLimitError,
)

from app.config import JEV_MODEL, JEV_PRICE_PER_1K_INPUT_USD
from app.models import Distribution
from app.providers.base import CallMeasure, JevAnswer, JevQuestion, ProviderCall, ProviderFailure
from app.providers.call_store import CallStore, Fetched, SpendCapReached, StoredCall
from app.providers.jev_wording import CRITERIA_BY_QUESTION

PROVIDER = "typesafe"
TIMEOUT_S = 5.0  # per attempt (U10)
RETRY = RetryPolicy(max_retries=1)  # two attempts with backoff (U10)


def build_request(state: str, questions: list[JevQuestion]) -> dict[str, Any]:
    """The exact request fields, which are also the call store's key. Criteria are lists of
    pairs: the key sorts dict keys, and the order sent is part of the request."""
    return {"state": state, "questions": [_question_fields(q) for q in questions]}


def _question_fields(question: JevQuestion) -> dict[str, Any]:
    if question.kind != "choice":
        raise ValueError(f"no runner asks Jev a {question.kind!r} question")
    known = CRITERIA_BY_QUESTION.get(question.id)
    if known is None:
        raise ValueError(f"no wording for Jev question {question.id!r}")
    unknown = sorted(set(question.options) - set(known))
    if unknown:
        raise ValueError(f"no wording for options {unknown} of Jev question {question.id!r}")
    chosen = set(question.options)
    return {"id": question.id, "instructions": question.prompt,
            "criteria": [[name, text] for name, text in known.items() if name in chosen]}


def _parse(response: SystemOneResponse, request: dict[str, Any]) -> dict[str, Any]:
    """What the store keeps. Raises ValueError on an answer that doesn't fit the question, so a
    bad answer fails the node and is never stored and replayed."""
    answers = {}
    for question in request["questions"]:
        answer = response.choices.get(question["id"])
        options = {name for name, _ in question["criteria"]}
        if answer is None or set(answer.probabilities) != options or answer.choice not in options:
            raise ValueError(f"answer does not fit question {question['id']!r}")
        total = sum(answer.probabilities.values())
        if total <= 0:
            raise ValueError(f"answer to {question['id']!r} has no probability")
        # The API's values sum to about 1; Distribution requires 1.
        answers[question["id"]] = {
            "value": answer.choice, "confidence": answer.confidence,
            "probabilities": {name: p / total for name, p in answer.probabilities.items()}}
    return {"model": response.model, "answers": answers}


def _failure(error: Exception, latency_ms: float) -> ProviderFailure:
    match error:
        case TypeSafeAPITimeoutError():
            return ProviderFailure("timeout", "Jev timed out", retryable=True,
                                   latency_ms=latency_ms)
        case TypeSafeRateLimitError():
            return ProviderFailure("rate_limited", "Jev rate limit reached", retryable=True,
                                   latency_ms=latency_ms)
        case TypeSafeAPIConnectionError():
            return ProviderFailure("provider_error", "could not reach Jev", retryable=True,
                                   latency_ms=latency_ms)
        case TypeSafeAPIResponseValidationError() | ValueError():
            return ProviderFailure("provider_error", "Jev returned an unusable answer",
                                   retryable=False, latency_ms=latency_ms)
        case TypeSafeAPIError():
            # The status only: the body may quote the request.
            return ProviderFailure("provider_error", f"Jev answered HTTP {error.status}",
                                   retryable=error.status >= 500, latency_ms=latency_ms)
        case _:
            return ProviderFailure("provider_error", f"Jev call failed: {type(error).__name__}",
                                   retryable=False, latency_ms=latency_ms)


class TypeSafeJevProvider:
    """Lives for one run, on that run's event loop: compute() builds it there and closes it."""

    def __init__(self, store: CallStore, api_key: str, *,
                 transport: httpx2.AsyncBaseTransport | None = None,
                 retry: RetryPolicy = RETRY,
                 clock: Callable[[], float] = time.perf_counter) -> None:
        self._store = store
        self._api_key = api_key
        self._transport = transport
        self._retry = retry
        self._clock = clock
        self._client: AsyncTypeSafeClient | None = None

    def _get_client(self) -> AsyncTypeSafeClient:
        # Made on the first real call, so a run that only replays opens no connection.
        if self._client is None:
            # Uncompressed: these requests are small, and zstd needs an extra on Python 3.12.
            self._client = AsyncTypeSafeClient(
                api_key=self._api_key, model=JEV_MODEL, retry=self._retry, timeout=TIMEOUT_S,
                transport=self._transport, compression=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()

    async def _fetch(self, request: dict[str, Any]) -> Fetched:
        started = self._clock()
        questions = {q["id"]: Choice(instructions=q["instructions"], criteria=dict(q["criteria"]))
                     for q in request["questions"]}
        try:
            response = await self._get_client().system_one(
                state=request["state"], questions=questions, model=JEV_MODEL)
            parsed = _parse(response, request)
        except (TypeSafeError, ValueError) as error:
            raise _failure(error, (self._clock() - started) * 1000) from error
        tokens_in = response.usage.input_tokens or 0
        return Fetched(response=parsed, tokens_in=tokens_in,
                       tokens_out=response.usage.output_tokens or 0,
                       cost_usd=tokens_in / 1000 * JEV_PRICE_PER_1K_INPUT_USD)

    async def ask(self, state: str, questions: list[JevQuestion],
                  call: ProviderCall) -> list[JevAnswer]:
        request = build_request(state, questions)
        try:
            stored = await self._store.call(PROVIDER, JEV_MODEL, request,
                                            partial(self._fetch, request))
        except SpendCapReached as error:
            raise ProviderFailure("spend_cap", str(error), retryable=False) from error
        return [_answer(q.id, stored) for q in questions]


def _answer(question_id: str, stored: StoredCall) -> JevAnswer:
    answer = stored.response["answers"][question_id]
    return JevAnswer(
        question_id=question_id, value=answer["value"], confidence=answer["confidence"],
        probabilities=Distribution(probs=answer["probabilities"]),
        measure=CallMeasure(latency_ms=stored.latency_ms, cost_usd=stored.cost_usd,
                            tokens_in=stored.tokens_in, tokens_out=stored.tokens_out,
                            replayed=stored.replayed))
