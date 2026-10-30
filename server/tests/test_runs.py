"""T20: practice runs over the API (decision Q6), stopping runs, and the run manager."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.catalog.default_graph import default_graph
from app.db import repo
from app.models import Graph, RunConfig
from app.simulation import manager
from app.simulation.loader import load_pack
from app.simulation.manager import runs
from app.simulation.runner import run_simulation
from test_ws import connect, receive_until_completed

FIXTURES = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "graphs"
FAST = {"speed": 1e6, "duration_s": 0.05}  # a whole practice run plays in about 0.1 s
SLOW = {"speed": 20.0, "duration_s": 45.0}  # the real timing: still playing when the test acts


@pytest.fixture
def client(live_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(manager, "PRACTICE_TIMING", FAST)
    return live_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def new_session(client: TestClient) -> tuple[str, str]:
    body = client.post("/api/sessions", json={"facilitatorCode": "open-sesame"}).json()
    return body["sessionCode"], body["facilitatorToken"]


def join(client: TestClient, code: str, name: str) -> dict[str, str]:
    return client.post(f"/api/sessions/{code}/teams", json={"teamName": name}).json()


def start(client: TestClient, team: dict[str, str]) -> Any:
    return client.post(f"/api/teams/{team['teamId']}/runs", headers=bearer(team["token"]))


def wait(client: TestClient, run_id: str) -> None:
    client.portal.call(runs.wait, run_id)


def latest(client: TestClient, team: dict[str, str]) -> dict[str, Any] | None:
    res = client.get(f"/api/teams/{team['teamId']}/runs/latest", headers=bearer(team["token"]))
    assert res.status_code == 200
    return res.json()


def stop(client: TestClient, run_id: str, token: str) -> Any:
    return client.post(f"/api/runs/{run_id}/stop", headers=bearer(token))


def save(client: TestClient, team: dict[str, str], graph: dict[str, Any]) -> None:
    headers = bearer(team["token"])
    version = client.get(f"/api/teams/{team['teamId']}/graph", headers=headers).json()["version"]
    res = client.put(f"/api/teams/{team['teamId']}/graph", json={"graph": graph, "version": version}, headers=headers)
    assert res.status_code == 200, res.text


def test_a_practice_run_plays_and_is_recorded(client: TestClient) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")
    ws = connect(client, red["token"])
    assert ws.receive_json()["type"] == "state_sync"
    assert latest(client, red) is None

    res = start(client, red)
    assert res.status_code == 201, res.text
    run = res.json()
    assert run["status"] == "running" and run["teamId"] == red["teamId"] and run["metrics"] is None
    assert run["config"]["mode"] == "practice" and run["config"]["packId"] == "practice"
    assert run["graphVersion"] == 0

    events = receive_until_completed(ws)
    assert events[0]["type"] == "run_started" and events[0]["runId"] == run["runId"]
    wait(client, run["runId"])
    done = latest(client, red)
    assert done["runId"] == run["runId"] and done["status"] == "completed"
    assert done["metrics"] == events[-1]["metrics"] and done["finishedAt"] is not None


def test_same_seed_same_metrics_as_a_headless_run(client: TestClient) -> None:
    """Determinism: the API run equals run_simulation on the same graph, pack and config."""
    code, _ = new_session(client)
    red = join(client, code, "Red")
    run = start(client, red).json()
    wait(client, run["runId"])
    config = RunConfig.model_validate(run["config"])
    expected = asyncio.run(run_simulation(default_graph(), load_pack("practice"), config))
    assert latest(client, red)["metrics"] == json.loads(expected.metrics.model_dump_json(by_alias=True))


def test_the_server_picks_a_new_seed_each_run(client: TestClient) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")
    seeds = set()
    for _ in range(3):
        run = start(client, red).json()
        wait(client, run["runId"])
        seeds.add(run["config"]["seed"])
    assert len(seeds) == 3


def test_the_run_uses_a_snapshot_of_the_stored_graph(client: TestClient, db: Session) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")
    strong = json.loads((FIXTURES / "strong.json").read_text())
    save(client, red, strong)
    run = start(client, red).json()
    assert run["graphVersion"] == 1
    wait(client, run["runId"])
    db.expire_all()
    assert Graph.model_validate(repo.get_run(db, run["runId"]).graph) == Graph.model_validate(strong)


def test_a_graph_with_errors_is_422_with_its_report(client: TestClient) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")
    save(client, red, json.loads((FIXTURES / "invalid-cycle.json").read_text()))
    res = start(client, red)
    assert res.status_code == 422
    report = res.json()
    assert report["ok"] is False and any(i["code"] == "CYCLE" for i in report["issues"])
    assert latest(client, red) is None


def test_a_locked_graph_is_423(client: TestClient) -> None:
    code, facilitator = new_session(client)
    red = join(client, code, "Red")
    client.post(f"/api/sessions/{code}/lock", json={"locked": True}, headers=bearer(facilitator))
    assert start(client, red).status_code == 423


def test_one_run_at_a_time_per_team(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager, "PRACTICE_TIMING", SLOW)
    code, _ = new_session(client)
    red, blue = join(client, code, "Red"), join(client, code, "Blue")
    first = start(client, red).json()
    assert start(client, red).status_code == 409
    assert start(client, blue).status_code == 201  # other teams are independent
    stop(client, first["runId"], red["token"])
    assert start(client, red).status_code == 201  # the slot is free again


def test_stop_ends_the_run_as_stopped(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager, "PRACTICE_TIMING", SLOW)
    code, _ = new_session(client)
    red = join(client, code, "Red")
    ws = connect(client, red["token"])
    ws.receive_json()
    run = start(client, red).json()

    res = stop(client, run["runId"], red["token"])
    assert res.status_code == 200
    stopped = res.json()
    assert stopped["status"] == "stopped" and stopped["finishedAt"] is not None
    assert stopped["metrics"]["total"] > stopped["metrics"]["completed"]
    events = receive_until_completed(ws)
    assert events[-1]["status"] == "stopped" and events[-1]["metrics"] == stopped["metrics"]
    assert stop(client, run["runId"], red["token"]).json() == stopped  # already ended: unchanged


def test_who_may_stop_a_run(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager, "PRACTICE_TIMING", SLOW)
    code, facilitator = new_session(client)
    _, other_facilitator = new_session(client)
    red, blue = join(client, code, "Red"), join(client, code, "Blue")
    run = start(client, red).json()
    assert stop(client, run["runId"], "not-a-token").status_code == 401
    assert stop(client, "no-such-run", red["token"]).status_code == 404
    assert stop(client, run["runId"], blue["token"]).status_code == 403
    assert stop(client, run["runId"], other_facilitator).status_code == 403
    res = stop(client, run["runId"], facilitator)
    assert res.status_code == 200 and res.json()["status"] == "stopped"


def test_teams_cannot_run_or_read_another_teams_runs(client: TestClient) -> None:
    code, _ = new_session(client)
    red, blue = join(client, code, "Red"), join(client, code, "Blue")
    assert client.post(f"/api/teams/{red['teamId']}/runs", headers=bearer(blue["token"])).status_code == 403
    assert client.get(f"/api/teams/{red['teamId']}/runs/latest", headers=bearer(blue["token"])).status_code == 403
    assert client.post(f"/api/teams/{red['teamId']}/runs").status_code == 401


def test_pencils_down_reaches_team_sockets_at_once(client: TestClient) -> None:
    code, facilitator = new_session(client)
    red = join(client, code, "Red")
    ws = connect(client, red["token"])
    ws.receive_json()
    client.post(f"/api/sessions/{code}/lock", json={"locked": True}, headers=bearer(facilitator))
    message = ws.receive_json()
    assert message["type"] == "graph_locked" and message["locked"] is True and message["teamId"] == red["teamId"]
    client.post(f"/api/sessions/{code}/lock", json={"locked": False}, headers=bearer(facilitator))
    assert ws.receive_json()["locked"] is False


def test_a_failed_setup_frees_the_slot(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")

    async def broken(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.api.runs.compute", broken)
    with pytest.raises(RuntimeError):
        start(client, red)
    monkeypatch.undo()
    monkeypatch.setattr(manager, "PRACTICE_TIMING", FAST)
    assert start(client, red).status_code == 201
    assert len([r for r in [latest(client, red)] if r]) == 1


def test_shutdown_records_runs_still_playing_as_stopped(client: TestClient, db: Session,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager, "PRACTICE_TIMING", SLOW)
    code, _ = new_session(client)
    red = join(client, code, "Red")
    run = start(client, red).json()
    client.portal.call(runs.shutdown)
    db.expire_all()
    assert repo.get_run(db, run["runId"]).status == "stopped"
