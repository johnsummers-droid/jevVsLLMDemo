"""T19: /api/ws — first-message auth, state_sync, channels, ordering, stop, reconnect (section 5)."""

import asyncio
import json
from functools import partial
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

import test_events as invariants  # tests/ is on sys.path (rootdir import mode)
from app.api import ws as ws_api
from app.config import Settings
from app.db import repo
from app.db.tables import TeamRow
from app.engine.pacer import Pacer
from app.models import RunConfig
from app.models.events import EventBase, GraphLocked, LeaderboardUpdated, ServerEvent
from app.realtime import hub as hub_module
from app.realtime.hub import FACILITATOR_EVENTS, Connection, hub
from app.simulation.loader import load_pack
from app.simulation.reference_graphs import strong_graph
from app.simulation.runner import run_simulation, stop_events

PACK = load_pack("practice")
_events: TypeAdapter[ServerEvent] = TypeAdapter(ServerEvent)


@pytest.fixture
def client(live_client: TestClient) -> TestClient:
    return live_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def new_session(client: TestClient) -> tuple[str, str]:
    body = client.post("/api/sessions", json={"facilitatorCode": "open-sesame"}).json()
    return body["sessionCode"], body["facilitatorToken"]


def join(client: TestClient, code: str, name: str) -> dict[str, str]:
    return client.post(f"/api/sessions/{code}/teams", json={"teamName": name}).json()


def connect(client: TestClient, token: str) -> WebSocketTestSession:
    ws = client.sockets.enter_context(client.websocket_connect("/api/ws"))  # type: ignore[attr-defined]
    ws.send_json({"type": "auth", "token": token})
    return ws


def wire(event: EventBase) -> dict[str, Any]:
    return json.loads(event.model_dump_json(by_alias=True))


def receive(ws: WebSocketTestSession, count: int) -> list[dict[str, Any]]:
    return [ws.receive_json() for _ in range(count)]


def receive_until_completed(ws: WebSocketTestSession) -> list[dict[str, Any]]:
    received = [ws.receive_json()]
    while received[-1]["type"] != "run_completed":
        received.append(ws.receive_json())
    return received


class Gate:
    """A pacer clock that never moves: every event after time 0 waits for a released token."""

    def __init__(self) -> None:
        self.tokens = asyncio.Semaphore(0)

    def clock(self) -> float:
        return 0.0

    async def sleep(self, _seconds: float) -> None:
        await self.tokens.acquire()


def start_run(client: TestClient, team_id: str, db: Session, *, run_id: str = "run-1",
              gate: Gate | None = None, seed: int = 1) -> Pacer:
    session_id = db.get(TeamRow, team_id).session_id

    async def start() -> Pacer:
        config = RunConfig(mode="practice", pack_id="practice", seed=seed,
                           speed=1e6, duration_s=0.05)  # arrivals over 50 ms, latencies ~0
        result = await run_simulation(strong_graph(), PACK, config, run_id=run_id, team_id=team_id)
        timing = {"clock": gate.clock, "sleep": gate.sleep} if gate else {}
        pacer = Pacer(result.events, config.speed, hub.publisher(session_id),
                      stop_events=partial(stop_events, result, PACK), **timing)
        pacer.start()
        return pacer

    return client.portal.call(start)


def make_gate(client: TestClient) -> Gate:
    async def make() -> Gate:
        return Gate()
    return client.portal.call(make)


def release(client: TestClient, gate: Gate, tokens: int) -> None:
    async def go() -> None:
        for _ in range(tokens):
            gate.tokens.release()
        for _ in range(50):
            await asyncio.sleep(0)
    client.portal.call(go)


def publish(client: TestClient, session_id: str, event: EventBase) -> None:
    async def go() -> None:
        hub.publish(session_id, event)
    client.portal.call(go)


@pytest.mark.parametrize("first", [None, {"type": "ping"}, {"type": "auth", "token": "nope"}, "not json"])
def test_missing_or_bad_auth_closes_4401(client: TestClient, monkeypatch: pytest.MonkeyPatch, first: Any) -> None:
    monkeypatch.setattr(ws_api, "AUTH_TIMEOUT_S", 0.05)
    with client.websocket_connect("/api/ws") as ws:
        if isinstance(first, dict):
            ws.send_json(first)
        elif first is not None:
            ws.send_text(first)
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == ws_api.CLOSE_AUTH


def test_unconfigured_secret_closes_1011(client: TestClient, settings: Settings) -> None:
    settings.token_secret = None
    with client.websocket_connect("/api/ws") as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == ws_api.CLOSE_UNCONFIGURED


def test_state_sync_is_first_and_carries_the_lock(client: TestClient) -> None:
    code, facilitator = new_session(client)
    red = join(client, code, "Red")
    first = connect(client, red["token"]).receive_json()
    assert first["type"] == "state_sync" and first["run"] is None and first["locked"] is False
    assert first["teamId"] == red["teamId"]

    client.post(f"/api/sessions/{code}/lock", json={"locked": True}, headers=bearer(facilitator))
    assert connect(client, red["token"]).receive_json()["locked"] is True
    first = connect(client, facilitator).receive_json()
    assert first["type"] == "state_sync" and first["locked"] is True and first["teamId"] is None


def test_a_team_receives_its_whole_run_in_order(client: TestClient, db: Session) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")
    ws = connect(client, red["token"])
    assert ws.receive_json()["type"] == "state_sync"
    pacer = start_run(client, red["teamId"], db)
    received = receive_until_completed(ws)
    assert received == [wire(e) for e in pacer.events]
    stream = [_events.validate_python(m) for m in received]
    for check in (invariants.test_run_started_first_and_run_completed_last,
                  invariants.test_node_started_before_it_finishes,
                  invariants.test_edges_transfer_only_after_their_source_completed):
        check(stream)
    assert [e.seq for e in stream] == list(range(len(stream)))


def test_channels_follow_the_token(client: TestClient, db: Session) -> None:
    code, facilitator = new_session(client)
    other_code, other_facilitator = new_session(client)
    red, blue = join(client, code, "Red"), join(client, code, "Blue")
    sockets = {name: connect(client, token) for name, token in
               [("red", red["token"]), ("blue", blue["token"]), ("fac", facilitator), ("other", other_facilitator)]}
    for ws in sockets.values():
        assert ws.receive_json()["type"] == "state_sync"

    red_run = start_run(client, red["teamId"], db, run_id="red-run")
    assert receive_until_completed(sockets["red"]) == [wire(e) for e in red_run.events]
    facilitator_view = [wire(e) for e in red_run.events if e.type in FACILITATOR_EVENTS]
    assert receive(sockets["fac"], len(facilitator_view)) == facilitator_view

    blue_run = start_run(client, blue["teamId"], db, run_id="blue-run")
    assert receive_until_completed(sockets["blue"]) == [wire(e) for e in blue_run.events]  # nothing of Red's

    marker = LeaderboardUpdated(seq=0, sim_ms=0, rows=[])
    publish(client, repo.get_session_by_code(db, other_code).id, marker)
    assert sockets["other"].receive_json() == wire(marker)  # nothing of this session's runs


def test_stop_mid_run_ends_with_stopped_and_then_silence(client: TestClient, db: Session) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")
    ws = connect(client, red["token"])
    ws.receive_json()
    gate = make_gate(client)
    pacer = start_run(client, red["teamId"], db, gate=gate)
    release(client, gate, 40)

    async def stop() -> bool:
        return await pacer.stop()
    assert client.portal.call(stop)
    release(client, gate, 10_000)

    received = receive_until_completed(ws)
    assert received[-1]["status"] == "stopped" and received[-2]["type"] == "metrics_snapshot"
    assert [m["seq"] for m in received] == list(range(len(received)))
    assert len(received) < len(pacer.events)

    session_id = db.get(TeamRow, red["teamId"]).session_id
    marker = GraphLocked(seq=0, sim_ms=0, team_id=red["teamId"], locked=True)
    publish(client, session_id, marker)
    assert ws.receive_json() == wire(marker)  # no run event slipped in after the stop


def test_reconnect_mid_run_replays_the_run_so_far(client: TestClient, db: Session) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")
    first = connect(client, red["token"])
    first.receive_json()
    gate = make_gate(client)
    pacer = start_run(client, red["teamId"], db, gate=gate)
    release(client, gate, 30)
    so_far = list(pacer.delivered)
    assert receive(first, len(so_far)) == [wire(e) for e in so_far]

    second = connect(client, red["token"])
    sync = second.receive_json()
    assert sync["type"] == "state_sync" and sync["seq"] == 0
    assert sync["run"]["runId"] == "run-1" and sync["run"]["status"] == "running"
    assert receive(second, len(so_far) - 1) == [wire(e) for e in so_far[1:]]

    release(client, gate, 10_000)
    rest = receive_until_completed(first)
    assert receive_until_completed(second) == rest
    assert [wire(e) for e in so_far] + rest == [wire(e) for e in pacer.events]


def test_a_finished_run_is_synced_from_its_totals(client: TestClient, db: Session) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")
    ws = connect(client, red["token"])
    ws.receive_json()
    pacer = start_run(client, red["teamId"], db)
    receive_until_completed(ws)

    sync = connect(client, red["token"]).receive_json()
    last, final_snapshot = pacer.events[-1], [e for e in pacer.events if e.type == "metrics_snapshot"][-1]
    assert sync["run"]["status"] == "completed" and sync["seq"] == last.seq
    assert sync["metrics"] == wire(last)["metrics"]
    assert sync["nodeStats"] == wire(final_snapshot)["nodeStats"]


def test_rejoining_closes_the_old_tokens_socket_4403(client: TestClient) -> None:
    code, _ = new_session(client)
    red = join(client, code, "Red")
    ws = connect(client, red["token"])
    ws.receive_json()
    join(client, code, "red")  # same team, new token (P3)
    with pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    assert closed.value.code == hub_module.CLOSE_REVOKED


def test_a_slow_socket_is_dropped_not_waited_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hub_module, "QUEUE_LIMIT", 3)
    conn = Connection("s", "t")
    for seq in range(4):
        conn.send(GraphLocked(seq=seq, sim_ms=0, team_id="t", locked=True))
    assert conn.close_code == hub_module.CLOSE_SLOW
    assert conn.queue.qsize() == 1 and conn.queue.get_nowait() is None
