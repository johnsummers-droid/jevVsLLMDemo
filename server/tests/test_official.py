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
    assert all(s == "pending" for t, s in statuses.items() if t != broken["teamId"])
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
    while completed < 3 or not boards or {r["status"] for r in boards[-1]} != {"completed"}:
        message = ws.receive_json()
        if message["type"] == "run_completed":
            completed += 1
        elif message["type"] == "leaderboard_updated":
            boards.append(message["rows"])
    assert [r["status"] for r in boards[0]] == ["pending"] * 3  # published right after the start
    assert boards[-1] == leaderboard(client, code, facilitator)
    assert [r["teamName"] for r in boards[-1]] == ["Strong", "Default", "Weak"]


def test_teams_see_their_own_official_run_but_never_the_pack_text(client: TestClient) -> None:
    code, facilitator, teams = three_teams(client)
    ws = connect(client, teams["Strong"]["token"])
    ws.receive_json()
    body = start_official(client, code, facilitator).json()
    assert ws.receive_json()["type"] == "graph_locked"
    events = receive_until_completed(ws)
    assert events[0]["type"] == "run_preparing" and events[0]["config"]["mode"] == "official"
    assert events[1]["type"] == "run_started"
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


def test_official_runs_start_together_after_all_are_computed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import anyio
    from app.api import official
    code, facilitator, teams = three_teams(client)
    ws = connect(client, facilitator)
    ws.receive_json()
    real, go = official.compute, []

    async def slow(*args: Any, **kwargs: Any) -> Any:
        if not go:
            go.append(anyio.Event())
        await go[0].wait()
        return await real(*args, **kwargs)

    monkeypatch.setattr("app.api.official.compute", slow)
    body = start_official(client, code, facilitator).json()
    assert {r["status"] for r in body["runs"]} == {"pending"}
    assert start_official(client, code, facilitator).status_code == 409  # still claimed
    client.portal.call(lambda: _release(go))
    wait_all(client, body)
    seen = []
    while sum(t == "run_completed" for t in seen) < 3:
        seen.append(ws.receive_json()["type"])
    assert seen.index("run_started") > max(i for i, t in enumerate(seen) if t == "run_preparing")


async def _release(go: list[Any]) -> None:
    import anyio
    if not go:
        go.append(anyio.Event())
    go[0].set()


def test_one_compute_failure_does_not_stop_the_others(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import official
    code, facilitator, teams = three_teams(client)
    real = official.compute

    async def flaky(*args: Any, **kwargs: Any) -> Any:
        if kwargs["team_id"] == teams["Weak"]["teamId"]:
            raise RuntimeError("boom")
        return await real(*args, **kwargs)

    monkeypatch.setattr("app.api.official.compute", flaky)
    body = start_official(client, code, facilitator).json()
    wait_all(client, body)
    rows = {r["teamName"]: r["status"] for r in leaderboard(client, code, facilitator)}
    assert rows == {"Strong": "completed", "Default": "completed", "Weak": "failed"}


def test_stopping_one_official_run_while_another_gets_ready(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A launched run is stopped through its pacer, even while later runs are still being marked."""
    import anyio
    from app.api import official
    monkeypatch.setattr(manager, "OFFICIAL_TIMING", SLOW)
    code, facilitator, teams = three_teams(client)
    gate: dict[str, Any] = {}
    real = official._mark_running
    marked: list[str] = []

    def mark(app: Any, run_id: str) -> None:
        marked.append(run_id)
        if len(marked) == 2:  # the first run is launched; the second waits here
            client.portal.call(gate["reached"].set)
            client.portal.call(gate["go"].wait)
        real(app, run_id)

    async def arm() -> None:
        gate["reached"], gate["go"] = anyio.Event(), anyio.Event()

    client.portal.call(arm)
    monkeypatch.setattr(official, "_mark_running", mark)
    body = start_official(client, code, facilitator).json()
    client.portal.call(gate["reached"].wait)
    try:
        res = client.post(f"/api/runs/{marked[0]}/stop", headers=bearer(facilitator))
    finally:
        client.portal.call(gate["go"].set)  # a failed assert below must not leave the mark waiting
    assert res.status_code == 200 and res.json()["status"] == "stopped"
    assert res.json()["metrics"] is not None  # stopped while playing, not while preparing
    for run in body["runs"]:
        client.post(f"/api/runs/{run['runId']}/stop", headers=bearer(facilitator))
