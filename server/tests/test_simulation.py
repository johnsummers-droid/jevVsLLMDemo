import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.catalog.default_graph import default_graph
from app.engine.executor import InvalidGraphError
from app.engine.validator import validate_graph
from app.models import Graph, RunConfig
from app.simulation.loader import load_pack
from app.simulation.reference_graphs import FIXTURE_GRAPHS, FIXTURES_DIR, REFERENCE_GRAPHS
from app.simulation.runner import run_simulation
from app.simulation.traffic import schedule, window_ms

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_headless  # noqa: E402

OFFICIAL = load_pack("official")


def config(**kw: object) -> RunConfig:
    return RunConfig(mode="practice", pack_id="official", seed=kw.pop("seed", 0), **kw)


# --- traffic ---------------------------------------------------------------------------------


def test_schedule_covers_the_pack_once_in_window_order() -> None:
    arrivals = schedule(OFFICIAL, config())
    assert Counter(a.ticket.id for a in arrivals) == Counter(t.id for t in OFFICIAL.tickets)
    times = [a.arrival_ms for a in arrivals]
    assert times == sorted(times) and 0 <= times[0] and times[-1] <= window_ms(config())
    assert len({a.request_id for a in arrivals}) == 30


def test_schedule_is_seeded() -> None:
    assert schedule(OFFICIAL, config(seed=1)) == schedule(OFFICIAL, config(seed=1))
    order = [a.ticket.id for a in schedule(OFFICIAL, config(seed=1))]
    assert order != [a.ticket.id for a in schedule(OFFICIAL, config(seed=2))]


def test_traffic_spike_and_injection_wave() -> None:
    assert len(schedule(OFFICIAL, config(traffic_spike=2.5))) == 75
    wave = schedule(OFFICIAL, config(injection_wave=True))
    assert len(wave) == 34
    assert Counter(a.ticket.category for a in wave)["prompt_injection"] == 8
    with pytest.raises(ValidationError):
        config(traffic_spike=4)


# --- runner ----------------------------------------------------------------------------------


def test_run_refuses_an_invalid_graph() -> None:
    graph = default_graph()
    graph.edges.clear()
    with pytest.raises(InvalidGraphError):
        asyncio.run(run_simulation(graph, OFFICIAL, config()))


def test_run_result_is_consistent() -> None:
    result = asyncio.run(run_simulation(REFERENCE_GRAPHS["strong"](), OFFICIAL, config()))
    assert result.status == "completed" and len(result.traces) == 30
    assert result.metrics.total == result.metrics.completed == 30
    assert [s.node_id for s in result.node_stats][0] == "customer_message"
    assert sum(s.requests for s in result.node_stats if s.node_id == "response") == 30


def test_run_is_deterministic() -> None:
    def run() -> object:
        return asyncio.run(run_simulation(REFERENCE_GRAPHS["strong"](), OFFICIAL,
                                          config(seed=5))).events

    assert run() == run()


# --- reference graphs ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_GRAPHS)
def test_reference_fixture_matches_code(name: str) -> None:
    fixture = Graph.model_validate(json.loads((FIXTURES_DIR / f"{name}.json").read_text()))
    assert fixture == REFERENCE_GRAPHS[name](), \
        "regenerate with: .venv/bin/python -m app.simulation.reference_graphs"


def test_reference_graphs_validate() -> None:
    for name, build in REFERENCE_GRAPHS.items():
        assert validate_graph(build()).ok, name
    strong_codes = {i.code.value for i in validate_graph(REFERENCE_GRAPHS["strong"]()).issues}
    assert "NO_SAFETY_COVERAGE" not in strong_codes and "NO_HUMAN_FALLBACK" not in strong_codes


# --- headless script ---------------------------------------------------------------------------


def test_headless_prints_metrics_and_node_stats(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_headless.main(["default", "official"]) == 0
    out = capsys.readouterr().out
    assert "default on official (seed 0)" in out and "p95_latency_ms" in out and "router" in out


def test_headless_json_mean_and_file_input(capsys: pytest.CaptureFixture[str]) -> None:
    path = str(FIXTURES_DIR / "strong.json")
    assert run_headless.main([path, "practice", "--seeds", "2", "--json"]) == 0
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["seeds"] == 2 and metrics["p95_latency_ms"] > 0


def test_headless_reports_invalid_graphs(tmp_path: Path,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    graph = default_graph()
    graph.edges.clear()
    path = tmp_path / "bad.json"
    path.write_text(graph.model_dump_json(by_alias=True))
    assert run_headless.main([str(path), "official"]) == 2
    assert "validation errors" in capsys.readouterr().err
