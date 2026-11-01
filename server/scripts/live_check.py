"""Ask the real provider about the practice pack and print how it does. Spends real money.

Usage (from server/, with TYPESAFE_API_KEY in server/.env and `alembic upgrade head` done):
    .venv/bin/python scripts/live_check.py jev
    .venv/bin/python scripts/live_check.py jev --all-intents
    .venv/bin/python scripts/live_check.py llm --tier small --show-replies   # also GEMINI_API_KEY

Calls go through the call store, so a rerun of the same questions replays and costs nothing, and
the daily spend cap applies. By default the router may pick the starter graph's allowed intents,
so a ticket whose expected intent is outside them can only be right by landing on low confidence.
The llm check sends each ticket straight to the answer generator with its default prompt, with no
router, docs or policy node, and prints what the scoring finds in each reply.
"""

import argparse
import asyncio
import random
import statistics
import sys
from dataclasses import dataclass
from functools import partial

from sqlalchemy.exc import SQLAlchemyError

from app.catalog.definitions.jev import INTENTS, JEV_INTENT_ROUTER
from app.catalog.definitions.llm import LLM_ANSWER_GENERATOR
from app.config import get_settings
from app.db.session import session_scope
from app.models import Ticket
from app.providers.base import (JevAnswer, JevQuestion, LLMReply, LLMRequest, ProviderCall,
                                ProviderFailure)
from app.providers.call_store import CallStore
from app.providers.jev_wording import INTENT_INSTRUCTIONS
from app.providers.typesafe_jev import TypeSafeJevProvider
from app.simulation.loader import load_pack


@dataclass(frozen=True)
class Row:
    ticket: Ticket
    answer: JevAnswer

    @property
    def correct(self) -> bool:
        return self.answer.value == self.ticket.expected_intent


def default_param(key: str):
    return next(p.default for p in JEV_INTENT_ROUTER.params if p.key == key)


def report(rows: list[Row], threshold: float) -> list[str]:
    """One line per ticket, then per category: accuracy, confidence, and what the gate would do."""
    lines = [f"{'ticket':8}{'category':18}{'expected':19}{'answer':19}{'conf':>6}{'ms':>7}  gate"]
    for row in rows:
        gate = "low_confidence" if row.answer.confidence < threshold else "route"
        mark = "" if row.correct else "  WRONG"
        lines.append(f"{row.ticket.id:8}{row.ticket.category:18}{row.ticket.expected_intent:19}"
                     f"{row.answer.value:19}{row.answer.confidence:6.2f}"
                     f"{row.answer.measure.latency_ms:7.0f}  {gate}{mark}")
    lines += ["", f"{'category':18}{'n':>3}{'right':>7}{'conf right':>12}{'conf wrong':>12}"
                  f"{'misrouted':>11}{'gated':>7}"]
    for category in sorted({row.ticket.category for row in rows}):
        group = [r for r in rows if r.ticket.category == category]
        lines.append(_summary_line(category, group, threshold))
    lines.append(_summary_line("all", rows, threshold))
    latencies = [r.answer.measure.latency_ms for r in rows]
    fresh = [r for r in rows if not r.answer.measure.replayed]
    lines += ["", f"threshold {threshold}. Latency median {statistics.median(latencies):.0f} ms, "
                  f"max {max(latencies):.0f} ms. {len(fresh)} real calls, "
                  f"${sum(r.answer.measure.cost_usd for r in fresh):.6f}."]
    return lines


def _summary_line(name: str, rows: list[Row], threshold: float) -> str:
    def mean(values: list[float]) -> str:
        return f"{statistics.mean(values):.2f}" if values else "-"
    right = [r.answer.confidence for r in rows if r.correct]
    wrong = [r.answer.confidence for r in rows if not r.correct]
    gated = sum(r.answer.confidence < threshold for r in rows)
    misrouted = sum(not r.correct and r.answer.confidence >= threshold for r in rows)
    return (f"{name:18}{len(rows):3}{len(right):7}{mean(right):>12}{mean(wrong):>12}"
            f"{misrouted:11}{gated:7}")


async def check_jev(all_intents: bool) -> list[str]:
    settings = get_settings()
    options = INTENTS if all_intents else default_param("allowed_intents")
    store = CallStore(partial(session_scope), settings.live_spend_cap_usd)
    jev = TypeSafeJevProvider(store, settings.typesafe_api_key)
    question = JevQuestion(id="intent", kind="choice", prompt=INTENT_INSTRUCTIONS, options=options)
    rows = []
    try:
        for ticket in load_pack("practice").tickets:
            [answer] = await jev.ask(ticket.text, [question], ProviderCall(ticket, random.Random(0)))
            rows.append(Row(ticket, answer))
    finally:
        await jev.aclose()
    return report(rows, default_param("threshold"))


def llm_report(rows: list[tuple[Ticket, LLMReply | ProviderFailure]],
               show_replies: bool = False) -> list[str]:
    """One line per ticket: time, tokens, taint and any judge verdict that isn't a clear no."""
    lines = [f"{'ticket':8}{'category':18}{'ms':>7}{'in':>6}{'out':>6}  taint / unsure or yes"]
    cost, fresh = 0.0, 0
    for ticket, reply in rows:
        if isinstance(reply, ProviderFailure):
            lines.append(f"{ticket.id:8}{ticket.category:18}{reply.latency_ms:7.0f}"
                         f"{'':12}  FAILED {reply.code}: {reply.message}")
            continue
        verdicts = " ".join(f"{rule}={p:.2f}" for rule, p in reply.verdicts.items() if p >= 0.3)
        taint = ",".join(sorted(reply.taint)) or "-"
        lines.append(f"{ticket.id:8}{ticket.category:18}{reply.measure.latency_ms:7.0f}"
                     f"{reply.tokens_in:6}{reply.tokens_out:6}  {taint}  {verdicts}".rstrip())
        if show_replies:
            lines.append(f"    | {reply.text}".replace("\n", "\n    | "))
        if not reply.measure.replayed:
            cost, fresh = cost + reply.measure.cost_usd, fresh + 1
    lines += ["", f"{fresh} real LLM calls, ${cost:.6f}, plus the judge's calls."]
    return lines


async def check_llm(tier: str, show_replies: bool) -> list[str]:
    from app.providers.gemini_llm import GeminiLLMProvider
    settings = get_settings()
    store = CallStore(partial(session_scope), settings.live_spend_cap_usd)
    judge = TypeSafeJevProvider(store, settings.typesafe_api_key)
    llm = GeminiLLMProvider(store, settings.gemini_api_key, judge)
    defaults = {p.key: p.default for p in LLM_ANSWER_GENERATOR.params}
    rows: list[tuple[Ticket, LLMReply | ProviderFailure]] = []
    try:
        for ticket in load_pack("practice").tickets:
            request = LLMRequest(model=tier, max_tokens=defaults["max_tokens"],
                                 prompt=defaults["prompt"], text=ticket.text)
            taint = frozenset({"injection"} if ticket.category == "prompt_injection" else set())
            try:
                rows.append((ticket, await llm.generate(
                    request, ProviderCall(ticket, random.Random(0), taint))))
            except ProviderFailure as failure:
                if failure.code == "spend_cap":
                    raise
                rows.append((ticket, failure))
    finally:
        await llm.aclose()
    return llm_report(rows, show_replies)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("provider", choices=["jev", "llm"])
    parser.add_argument("--all-intents", action="store_true",
                        help="let the router pick any intent, not only the starter graph's")
    parser.add_argument("--tier", choices=["small", "large"], default="small")
    parser.add_argument("--show-replies", action="store_true", help="print each reply's text")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.typesafe_api_key:
        print("TYPESAFE_API_KEY is not set (server/.env)", file=sys.stderr)
        return 2
    if args.provider == "llm" and not settings.gemini_api_key:
        print("GEMINI_API_KEY is not set (server/.env)", file=sys.stderr)
        return 2
    try:
        if args.provider == "jev":
            lines = asyncio.run(check_jev(args.all_intents))
        else:
            lines = asyncio.run(check_llm(args.tier, args.show_replies))
    except ProviderFailure as failure:
        print(f"{failure.code}: {failure.message}", file=sys.stderr)
        return 1
    except SQLAlchemyError as error:
        print(f"database problem, has `alembic upgrade head` run? {type(error).__name__}",
              file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
