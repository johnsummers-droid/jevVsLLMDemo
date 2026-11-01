"""Run a graph against a scenario pack without the UI and print the metrics.

Usage (from server/):
    .venv/bin/python scripts/run_headless.py default official
    .venv/bin/python scripts/run_headless.py ../shared/fixtures/graphs/strong.json practice --seed 3
    .venv/bin/python scripts/run_headless.py strong official --seeds 10   # mean over seeds 0..9

GRAPH is a reference graph name (default, weak, strong, escalate_all) or a path to a graph
JSON file. Used to tune the mocks and scoring weights (plan1.txt M1).

--live uses real Jev and Gemini through the call store: it spends real money on anything not stored
yet, within the daily cap. A real answer doesn't depend on the seed, but simulated latency of
tools and human review does.
"""

import argparse
import asyncio
import json
import statistics
import sys
from functools import partial
from pathlib import Path

from app.config import get_settings
from app.db.session import session_scope
from app.engine.executor import InvalidGraphError
from app.models import Graph, RunConfig
from app.providers.factory import close_provider, jev_provider, llm_provider, new_call_store
from app.simulation.loader import PACK_IDS, load_pack
from app.simulation.reference_graphs import REFERENCE_GRAPHS
from app.simulation.runner import RunResult, run_simulation

METRIC_FIELDS = ["automation_rate", "escalation_rate", "unsafe_release_rate", "dropped_rate",
                 "p50_latency_ms", "p95_latency_ms", "cost_per_1k_usd", "decision_quality",
                 "score"]


def load_graph(name_or_path: str) -> Graph:
    if name_or_path in REFERENCE_GRAPHS:
        return REFERENCE_GRAPHS[name_or_path]()
    return Graph.model_validate(json.loads(Path(name_or_path).read_text()))


def run(graph: Graph, pack_id: str, seed: int, live: bool = False) -> RunResult:
    config = RunConfig(mode="practice", pack_id=pack_id, seed=seed)
    if not live:
        return asyncio.run(run_simulation(graph, load_pack(pack_id), config))

    async def run_live() -> RunResult:
        settings = get_settings().model_copy(update={"jev_mode": "live", "llm_mode": "live"})
        store = new_call_store(settings, partial(session_scope))
        jev, llm = jev_provider(settings, store), llm_provider(settings, store)
        try:
            return await run_simulation(graph, load_pack(pack_id), config, jev=jev, llm=llm)
        finally:
            await close_provider(jev)
            await close_provider(llm)

    return asyncio.run(run_live())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("graph")
    parser.add_argument("pack", choices=PACK_IDS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seeds", type=int, help="average over seeds 0..N-1")
    parser.add_argument("--json", action="store_true", help="print metrics as JSON")
    parser.add_argument("--live", action="store_true", help="real providers; spends real money")
    args = parser.parse_args(argv)

    graph = load_graph(args.graph)
    seeds = list(range(args.seeds)) if args.seeds else [args.seed]
    try:
        results = [run(graph, args.pack, seed, args.live) for seed in seeds]
    except InvalidGraphError as exc:
        print(exc, file=sys.stderr)
        return 2

    if len(results) == 1:
        metrics = results[0].metrics.model_dump()
    else:
        metrics = {f: statistics.mean(getattr(r.metrics, f) for r in results)
                   for f in METRIC_FIELDS}
        metrics["seeds"] = len(results)
    if args.json:
        print(json.dumps(metrics, indent=2))
        return 0

    label = f"seed {args.seed}" if len(results) == 1 else f"mean of {len(results)} seeds"
    print(f"{args.graph} on {args.pack} ({label})")
    for field in METRIC_FIELDS:
        print(f"  {field:<22} {metrics[field]:>10.3f}")
    if len(results) == 1:
        print("\n  node                    runs  skip   avg ms    cost $  decisions")
        for s in results[0].node_stats:
            decisions = ", ".join(f"{k}={v}" for k, v in sorted(s.decisions.items()))
            print(f"  {s.node_id:<22} {s.requests:>5} {s.skipped:>5} {s.avg_latency_ms:>8.0f}"
                  f" {s.total_cost_usd:>9.4f}  {decisions}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
