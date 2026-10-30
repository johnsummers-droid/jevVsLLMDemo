"""T13: a team's graph through the API — versions, locks, isolation."""

import pytest
from fastapi.testclient import TestClient

from app.catalog.default_graph import default_graph
from app.models.graph import MAX_NODES, Graph

CODE = "open-sesame"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def session(db_client: TestClient) -> dict[str, str]:
    body = db_client.post("/api/sessions", json={"facilitatorCode": CODE}).json()
    return {"code": body["sessionCode"], "facilitator": body["facilitatorToken"]}


def join(client: TestClient, code: str, name: str) -> tuple[str, dict[str, str]]:
    body = client.post(f"/api/sessions/{code}/teams", json={"teamName": name}).json()
    return body["teamId"], bearer(body["token"])


def smaller() -> dict:
    graph = default_graph()
    return Graph(nodes=graph.nodes[:2], edges=[]).model_dump(by_alias=True, mode="json")


def put(client: TestClient, team_id: str, headers: dict[str, str], version: int, graph: dict):
    return client.put(f"/api/teams/{team_id}/graph", json={"version": version, "graph": graph}, headers=headers)


def lock(client: TestClient, session: dict[str, str], locked: bool) -> None:
    res = client.post(f"/api/sessions/{session['code']}/lock", json={"locked": locked}, headers=bearer(session["facilitator"]))
    assert res.status_code == 200


def test_get_returns_default_graph_at_version_0(db_client: TestClient, session: dict[str, str]) -> None:
    team_id, headers = join(db_client, session["code"], "Red")
    res = db_client.get(f"/api/teams/{team_id}/graph", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["teamId"] == team_id and body["version"] == 0 and body["locked"] is False
    assert Graph.model_validate(body["graph"]) == default_graph()


def test_put_bumps_version_and_persists(db_client: TestClient, session: dict[str, str]) -> None:
    team_id, headers = join(db_client, session["code"], "Red")
    res = put(db_client, team_id, headers, 0, smaller())
    assert res.status_code == 200 and res.json()["version"] == 1
    again = db_client.get(f"/api/teams/{team_id}/graph", headers=headers).json()
    assert again["version"] == 1 and again["graph"] == smaller()
    assert put(db_client, team_id, headers, 1, smaller()).json()["version"] == 2


def test_invalid_graph_can_be_saved(db_client: TestClient, session: dict[str, str]) -> None:
    """P7: work in progress is saved; only the shape is checked."""
    team_id, headers = join(db_client, session["code"], "Red")
    assert put(db_client, team_id, headers, 0, {"nodes": [], "edges": []}).status_code == 200


@pytest.mark.parametrize("version", [0, 2])
def test_stale_version_is_409_with_current_graph(db_client: TestClient, session: dict[str, str], version: int) -> None:
    team_id, headers = join(db_client, session["code"], "Red")
    current = put(db_client, team_id, headers, 0, smaller()).json()
    res = put(db_client, team_id, headers, version, {"nodes": [], "edges": []})
    assert res.status_code == 409
    assert res.json() == current


def test_locked_graph_refuses_put_and_reset_with_423(db_client: TestClient, session: dict[str, str]) -> None:
    team_id, headers = join(db_client, session["code"], "Red")
    lock(db_client, session, True)
    assert put(db_client, team_id, headers, 0, smaller()).status_code == 423
    assert db_client.post(f"/api/teams/{team_id}/graph/reset", headers=headers).status_code == 423
    # Reading still works, and shows the lock.
    assert db_client.get(f"/api/teams/{team_id}/graph", headers=headers).json()["locked"] is True
    lock(db_client, session, False)
    assert put(db_client, team_id, headers, 0, smaller()).status_code == 200


def test_locked_beats_stale(db_client: TestClient, session: dict[str, str]) -> None:
    team_id, headers = join(db_client, session["code"], "Red")
    put(db_client, team_id, headers, 0, smaller())
    lock(db_client, session, True)
    assert put(db_client, team_id, headers, 0, smaller()).status_code == 423


def test_reset_restores_default_and_old_version_is_then_stale(db_client: TestClient, session: dict[str, str]) -> None:
    team_id, headers = join(db_client, session["code"], "Red")
    put(db_client, team_id, headers, 0, smaller())
    res = db_client.post(f"/api/teams/{team_id}/graph/reset", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 2 and Graph.model_validate(body["graph"]) == default_graph()
    stale = put(db_client, team_id, headers, 1, smaller())
    assert stale.status_code == 409 and stale.json()["version"] == 2


@pytest.mark.parametrize(
    "body",
    [
        {"version": 0},
        {"version": -1, "graph": {"nodes": [], "edges": []}},
        {"version": 0, "graph": {"nodes": "x", "edges": []}},
        {"version": 0, "graph": {"nodes": [], "edges": [], "extra": 1}},
    ],
)
def test_malformed_body_is_422(db_client: TestClient, session: dict[str, str], body: dict) -> None:
    team_id, headers = join(db_client, session["code"], "Red")
    assert db_client.put(f"/api/teams/{team_id}/graph", json=body, headers=headers).status_code == 422


def test_too_large_graph_is_422(db_client: TestClient, session: dict[str, str]) -> None:
    team_id, headers = join(db_client, session["code"], "Red")
    node = smaller()["nodes"][0]
    nodes = [{**node, "id": f"n{i}"} for i in range(MAX_NODES + 1)]
    assert put(db_client, team_id, headers, 0, {"nodes": nodes, "edges": []}).status_code == 422


def test_teams_are_isolated(db_client: TestClient, session: dict[str, str]) -> None:
    red_id, red = join(db_client, session["code"], "Red")
    blue_id, blue = join(db_client, session["code"], "Blue")
    put(db_client, red_id, red, 0, smaller())

    assert db_client.get(f"/api/teams/{blue_id}/graph", headers=blue).json()["version"] == 0
    assert db_client.get(f"/api/teams/{blue_id}/graph", headers=red).status_code == 403
    assert put(db_client, blue_id, red, 0, smaller()).status_code == 403
    assert db_client.post(f"/api/teams/{blue_id}/graph/reset", headers=red).status_code == 403
    assert db_client.get(f"/api/teams/{blue_id}/graph", headers=blue).json()["version"] == 0


def test_auth_is_required(db_client: TestClient, session: dict[str, str]) -> None:
    team_id, _ = join(db_client, session["code"], "Red")
    assert db_client.get(f"/api/teams/{team_id}/graph").status_code == 401
    # A facilitator token is real but not a team token.
    assert db_client.get(f"/api/teams/{team_id}/graph", headers=bearer(session["facilitator"])).status_code == 403


def test_rejoined_team_keeps_its_graph_and_old_token_stops_working(db_client: TestClient, session: dict[str, str]) -> None:
    team_id, old = join(db_client, session["code"], "Red")
    put(db_client, team_id, old, 0, smaller())
    same_id, new = join(db_client, session["code"], "red")
    assert same_id == team_id
    assert db_client.get(f"/api/teams/{team_id}/graph", headers=old).status_code == 401
    assert db_client.get(f"/api/teams/{team_id}/graph", headers=new).json()["graph"] == smaller()
