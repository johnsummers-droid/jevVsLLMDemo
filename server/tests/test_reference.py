"""T40: reference graphs for the facilitator, and for teams after the official run."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import repo
from app.simulation.manager import OFFICIAL_TIMING  # noqa: F401  (patched by the client fixture)
from app.simulation.reference_graphs import REFERENCE_GRAPHS
from test_official import client, start_official, wait_all  # noqa: F401  (client is a fixture)
from test_runs import bearer, join, new_session

NAMES = ["default", "weak", "strong", "escalate_all"]


def team_list(client: TestClient, team: dict[str, str]) -> Any:
    res = client.get(f"/api/teams/{team['teamId']}/reference-graphs", headers=bearer(team["token"]))
    assert res.status_code == 200
    return res.json()


def team_graph(client: TestClient, team: dict[str, str], name: str = "strong") -> Any:
    return client.get(f"/api/teams/{team['teamId']}/reference-graphs/{name}", headers=bearer(team["token"]))


def test_facilitator_sees_every_graph_at_any_time(client: TestClient) -> None:
    code, facilitator = new_session(client)
    listing = client.get(f"/api/sessions/{code}/reference-graphs", headers=bearer(facilitator)).json()
    assert listing["available"] is True
    assert [g["name"] for g in listing["graphs"]] == NAMES
    assert all(g["label"] for g in listing["graphs"])
    for name in NAMES:
        res = client.get(f"/api/sessions/{code}/reference-graphs/{name}", headers=bearer(facilitator))
        assert res.status_code == 200
        assert res.json() == REFERENCE_GRAPHS[name]().model_dump(by_alias=True, mode="json")


def test_session_endpoints_are_for_this_sessions_facilitator(client: TestClient) -> None:
    code, facilitator = new_session(client)
    _, other = new_session(client)
    team = join(client, code, "Red")
    url = f"/api/sessions/{code}/reference-graphs"
    assert client.get(f"{url}/strong").status_code == 401
    assert client.get(f"{url}/strong", headers=bearer("nonsense")).status_code == 401
    assert client.get(f"{url}/strong", headers=bearer(other)).status_code == 403
    assert client.get(f"{url}/strong", headers=bearer(team["token"])).status_code == 403
    assert client.get(url, headers=bearer(team["token"])).status_code == 403
    assert client.get(f"{url}/nope", headers=bearer(facilitator)).status_code == 404


def test_teams_are_refused_until_the_official_run_has_ended(client: TestClient) -> None:
    code, facilitator = new_session(client)
    team = join(client, code, "Red")

    def refused() -> None:
        assert team_list(client, team) == {"available": False, "graphs": []}
        assert team_graph(client, team).status_code == 403
        assert team_graph(client, team, "nope").status_code == 403  # names aren't revealed either

    refused()  # editing
    client.post(f"/api/sessions/{code}/lock", json={"locked": True}, headers=bearer(facilitator))
    refused()  # pencils down, no official run yet

    started = start_official(client, code, facilitator)
    assert started.status_code in (200, 201)
    wait_all(client, started.json())

    listing = team_list(client, team)
    assert listing["available"] is True
    assert [g["name"] for g in listing["graphs"]] == NAMES
    res = team_graph(client, team)
    assert res.status_code == 200
    assert res.json() == REFERENCE_GRAPHS["strong"]().model_dump(by_alias=True, mode="json")
    assert team_graph(client, team, "nope").status_code == 404

    client.post(f"/api/sessions/{code}/lock", json={"locked": False}, headers=bearer(facilitator))
    refused()  # unlocking ends the reveal


def test_not_revealed_while_a_teams_official_run_is_unfinished(client: TestClient, db: Session) -> None:
    code, facilitator = new_session(client)
    red, blue = join(client, code, "Red"), join(client, code, "Blue")
    started = start_official(client, code, facilitator)
    wait_all(client, started.json())
    assert team_list(client, red)["available"] is True

    run_id = started.json()["runs"][1]["runId"]
    row = repo.get_run(db, run_id)
    assert row is not None
    row.status = "running"
    db.commit()
    assert team_list(client, red)["available"] is False
    assert team_graph(client, blue).status_code == 403


def test_a_team_cannot_ask_as_another_team(client: TestClient) -> None:
    code, _ = new_session(client)
    red, blue = join(client, code, "Red"), join(client, code, "Blue")
    url = f"/api/teams/{red['teamId']}/reference-graphs"
    assert client.get(url, headers=bearer(blue["token"])).status_code == 403
    assert client.get(url).status_code == 401
