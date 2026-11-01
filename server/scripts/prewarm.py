"""Fill the call store ahead of a workshop, so runs of the reference graphs start at once.

Spends real money, once: every call is stored, and a rerun replays for free. It writes to the
database in DATABASE_URL, so to warm production run it where that points at production.

Usage (from server/, with JEV_MODE=live and/or LLM_MODE=live and their keys in the environment):
    .venv/bin/python scripts/prewarm.py                      # both packs, all reference graphs
    .venv/bin/python scripts/prewarm.py --packs practice --graphs default strong

The seed doesn't matter: a real request's key holds its text and parameters, not the seed.
"""

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime
from functools import partial

from app.config import get_settings
from app.db import repo
from app.db.session import session_scope
from app.models import RunConfig
from app.providers.call_store import start_of_day
from app.providers.factory import close_provider, jev_provider, llm_provider, new_call_store
from app.simulation.loader import PACK_IDS, load_pack
from app.simulation.reference_graphs import REFERENCE_GRAPHS
from app.simulation.runner import run_simulation


def spent_today() -> float:
    with session_scope() as db:
        return repo.spend_since(db, start_of_day(datetime.now(UTC)))


async def prewarm(packs: list[str], graphs: list[str]) -> list[str]:
    settings = get_settings()
    store = new_call_store(settings, partial(session_scope))
    lines = []
    for pack_id in packs:
        pack = load_pack(pack_id)
        for name in graphs:
            jev, llm = jev_provider(settings, store), llm_provider(settings, store)
            before, started = await asyncio.to_thread(spent_today), time.perf_counter()
            try:
                config = RunConfig(mode="practice", pack_id=pack_id, seed=0)
                result = await run_simulation(REFERENCE_GRAPHS[name](), pack, config, jev=jev, llm=llm)
            finally:
                await close_provider(jev)
                await close_provider(llm)
            failed = sum(t.outcome == "failed" for t in result.traces)
            spent = await asyncio.to_thread(spent_today) - before
            lines.append(f"{pack_id:9}{name:14}{time.perf_counter() - started:7.1f} s  "
                         f"${spent:.4f}  {failed} failed")
            if result.events[0].warnings:
                lines.append("  stopped: " + result.events[0].warnings[0])
                return lines
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--packs", nargs="+", choices=sorted(PACK_IDS), default=sorted(PACK_IDS))
    parser.add_argument("--graphs", nargs="+", choices=sorted(REFERENCE_GRAPHS),
                        default=sorted(REFERENCE_GRAPHS))
    args = parser.parse_args()
    settings = get_settings()
    if problems := settings.live_problems():
        print("; ".join(problems), file=sys.stderr)
        return 2
    if "live" not in (settings.jev_mode, settings.llm_mode):
        print("nothing to warm: set JEV_MODE=live and/or LLM_MODE=live", file=sys.stderr)
        return 2
    print("\n".join(asyncio.run(prewarm(args.packs, args.graphs))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
