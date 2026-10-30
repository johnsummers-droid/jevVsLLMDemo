"""T21: official runs (decision Q7) and the leaderboard."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import LeaderboardRow, RunMetrics
from app.simulation import manager
from app.simulation.loader import load_pack
from app.simulation.scoring import Standing, rank
from test_runs import FAST, SLOW, bearer, join, new_session, save, start, wait
from test_ws import connect, receive_until_completed

FIXTURES = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "graphs"
SEED = 3  # the golden tests pin weak < default < strong on every seed in range(10)


@pytest.fixture
def client(live_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(manager, "PRACTICE_TIMING", FAST)
    monkeypatch.setattr(manager, "OFFICIAL_TIMING", FAST)
    monkeypatch.setattr(manager, "new_seed", lambda: SEED)
    return live_client


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def start_official(client: TestClient, code: str, facilitator: str) -> Any:
    return client.post(f"/api/sessions/{code}/runs", headers=bearer(facilitator))


def wait_all(client: TestClient, body: dict[str, Any]) -> None:
    for run in body["runs"]:
        wait(client, run["runId"])


def leaderboard(client: TestClient, code: str, facilitator: str) -> list[dict[str, Any]]:
    res = client.get(f"/api/sessions/{code}/leaderboard", headers=bearer(facilitator))
    assert res.status_code == 200, res.text
    return res.json()


def three_teams(client: TestClient) -> tuple[str, str, dict[str, dict[str, str]]]:
    code, facilitator = new_session(client)
    teams = {name: join(client, code, name) for name in ("Default", "Weak", "Strong")}
    save(client, teams["Weak"], fixture("weak"))
    save(client, teams["Strong"], fixture("strong"))
    return code, facilitator, teams


def test_teams_finish_in_the_golden_order(client: TestClient) -> None:
    """The T21 exit: default, weak and strong graphs rank strong > default > weak."""
    code, facilitator, teams = three_teams(client)
    res = start_official(client, code, facilitator)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["seed"] == SEED and len(body["runs"]) == 3
    wait_all(client, body)
    rows = leaderboard(client, code, facilitator)
    assert [r["teamName"] for r in rows] == ["Strong", "Default", "Weak"]
    assert [r["rank"] for r in rows] == [1, 2, 3]
    assert all(r["status"] == "completed" and r["metrics"]["total"] > 0 for r in rows)
    scores = [r["metrics"]["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_every_team_gets_the_same_seed_and_config_on_the_official_pack(client: TestClient) -> None:
    code, facilitator, _ = three_teams(client)
    body = start_official(client, code, facilitator).json()
    configs = {json.dumps(run["config"], sort_keys=True) for run in body["runs"]}
    assert len(configs) == 1
    config = json.loads(configs.pop())
    assert config["mode"] == "official" and config["packId"] == "official" and config["seed"] == SEED
    wait_all(client, body)


def test_starting_locks_the_session(client: TestClient) -> None:
    code, facilitator, teams = three_teams(client)
    ws = connect(client, teams["Default"]["token"])
    ws.receive_json()
    body = start_official(client, code, facilitator).json()
    assert ws.receive_json()["type"] == "graph_locked"
    assert start(client, teams["Default"]).status_code == 423  # no practice runs now
    detail = client.get(f"/api/sessions/{code}", headers=bearer(facilitator)).json()
    assert detail["locked"] is True
    wait_all(client, body)


def test_a_graph_with_errors_runs_as_failed_and_ranks_last(client: TestClient) -> None:
    code, facilitator, teams = three_teams(client)
    broken = join(client, code, "Broken")
    save(client, broken, fixture("invalid-cycle"))
    body = start_official(client, code, facilitator).json()
    statuses = {run["teamId"]: run["status"] for run in body["runs"]}
    assert statuses[broken["teamId"]] == "failed"
    assert all(s == "running" for t, s in statuses.items() if t != broken["teamId"])
    wait_all(client, body)
    rows = leaderboard(client, code, facilitator)
    assert rows[-1]["teamName"] == "Broken" and rows[-1]["status"] == "failed" and rows[-1]["metrics"] is None


def test_a_practice_run_in_progress_is_stopped_first(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    code, facilitator, teams = three_teams(client)
    monkeypatch.setattr(manager, "PRACTICE_TIMING", SLOW)
    practice = start(client, teams["Default"]).json()
    body = start_official(client, code, facilitator).json()
    latest = client.get(f"/api/teams/{teams['Default']['teamId']}/runs/latest",
                        headers=bearer(teams["Default"]["token"])).json()
    assert latest["config"]["mode"] == "official"
    stopped = [r for r in body["runs"] if r["teamId"] == teams["Default"]["teamId"]][0]
    assert stopped["runId"] != practice["runId"]
    wait_all(client, body)
    res = client.post(f"/api/runs/{practice['runId']}/stop", headers=bearer(teams["Default"]["token"]))
    assert res.json()["status"] == "stopped"


def test_one_official_run_at_a_time(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager, "OFFICIAL_TIMING", SLOW)
    code, facilitator, _ = three_teams(client)
    body = start_official(client, code, facilitator).json()
    assert start_official(client, code, facilitator).status_code == 409
    for run in body["runs"]:
        client.post(f"/api/runs/{run['runId']}/stop", headers=bearer(facilitator))
    assert start_official(client, code, facilitator).status_code == 201  # free again once all ended


def test_only_the_sessions_facilitator(client: TestClient) -> None:
    code, _, teams = three_teams(client)
    _, other_facilitator = new_session(client)
    assert start_official(client, code, teams["Default"]["token"]).status_code == 403
    assert start_official(client, code, other_facilitator).status_code == 403
    assert start_official(client, code, "nope").status_code == 401
    assert client.get(f"/api/sessions/{code}/leaderboard", headers=bearer(other_facilitator)).status_code == 403


def test_the_facilitator_socket_gets_the_leaderboard_as_teams_finish(client: TestClient) -> None:
    code, facilitator, teams = three_teams(client)
    ws = connect(client, facilitator)
    ws.receive_json()  # state_sync; graph_locked goes to team sockets only
    body = start_official(client, code, facilitator).json()
    wait_all(client, body)
    boards: list[list[dict[str, Any]]] = []
    completed = 0
    while completed < 3 or len(boards) < 4:
        message = ws.receive_json()
        if message["type"] == "run_completed":
            completed += 1
        elif message["type"] == "leaderboard_updated":
            boards.append(message["rows"])
    assert [r["status"] for r in boards[0]] == ["running"] * 3  # published right after the start
    assert boards[-1] == leaderboard(client, code, facilitator)
    assert [r["teamName"] for r in boards[-1]] == ["Strong", "Default", "Weak"]


def test_teams_see_their_own_official_run_but_never_the_pack_text(client: TestClient) -> None:
    code, facilitator, teams = three_teams(client)
    ws = connect(client, teams["Strong"]["token"])
    ws.receive_json()
    body = start_official(client, code, facilitator).json()
    assert ws.receive_json()["type"] == "graph_locked"
    events = receive_until_completed(ws)
    assert events[0]["type"] == "run_started" and events[0]["config"]["mode"] == "official"
    assert {e["teamId"] for e in events} == {teams["Strong"]["teamId"]}
    wire = json.dumps(events) + json.dumps(body) + json.dumps(leaderboard(client, code, facilitator))
    for ticket in load_pack("official").tickets:
        assert ticket.text not in wire
    wait_all(client, body)


def metrics(score: float, unsafe: float = 0.0, p95: float = 500.0) -> RunMetrics:
    return RunMetrics(total=30, completed=30, automation_rate=0.5, escalation_rate=0.2, unsafe_release_rate=unsafe,
                      dropped_rate=0.0, p50_latency_ms=300, p95_latency_ms=p95, cost_per_1k_usd=90,
                      decision_quality=0.9, score=score)


def test_ranking_rules() -> None:
    rows: list[LeaderboardRow] = rank([
        Standing("f", "Failed", "r6", "failed", None),
        Standing("r", "Running", "r5", "running", None),
        Standing("s", "Stopped", "r4", "stopped", metrics(99)),
        Standing("b", "Safer", "r3", "completed", metrics(50, unsafe=0.0)),
        Standing("a", "Riskier", "r2", "completed", metrics(50, unsafe=0.1)),
        Standing("t", "Top", "r1", "completed", metrics(70)),
    ])
    assert [r.team_name for r in rows] == ["Top", "Safer", "Riskier", "Stopped", "Running", "Failed"]
    assert [r.rank for r in rows] == [1, 2, 3, 4, 5, 6]
