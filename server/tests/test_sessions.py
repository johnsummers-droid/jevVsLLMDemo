"""T12: sessions, teams and bearer-token auth through the API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.catalog.default_graph import default_graph
from app.config import Settings, get_settings
from app.db import repo
from app.db.tables import SessionRow, TeamRow
from app.main import app
from app.models.sessions import MAX_TEAMS_PER_SESSION

CODE = "open-sesame"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_session(client: TestClient) -> tuple[str, str]:
    res = client.post("/api/sessions", json={"facilitatorCode": CODE})
    assert res.status_code == 201, res.text
    body = res.json()
    return body["sessionCode"], body["facilitatorToken"]


def join(client: TestClient, code: str, name: str) -> dict:
    res = client.post(f"/api/sessions/{code}/teams", json={"teamName": name})
    assert res.status_code == 201, res.text
    return res.json()


def test_create_session_returns_code_and_token(db_client: TestClient) -> None:
    code, token = create_session(db_client)
    assert len(code) == auth.CODE_LENGTH and set(code) <= set(auth.CODE_ALPHABET)
    assert not set(code) & set("0O1IL")
    assert len(token) >= 40


def test_wrong_facilitator_code_is_401(db_client: TestClient) -> None:
    res = db_client.post("/api/sessions", json={"facilitatorCode": "open-sesam"})
    assert res.status_code == 401


@pytest.mark.parametrize("unset", ["facilitator_code", "token_secret"])
def test_create_session_refused_while_secrets_unset(db_client: TestClient, settings: Settings, unset: str) -> None:
    app.dependency_overrides[get_settings] = lambda: settings.model_copy(update={unset: None})
    assert db_client.post("/api/sessions", json={"facilitatorCode": CODE}).status_code == 503


def test_session_code_collision_retries(db_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    taken, _ = create_session(db_client)
    codes = iter([taken, taken, "ABCDEF"])
    monkeypatch.setattr(auth, "new_session_code", lambda: next(codes))
    assert create_session(db_client)[0] == "ABCDEF"


def test_join_gives_team_with_default_graph_at_version_0(db_client: TestClient, db: Session) -> None:
    code, _ = create_session(db_client)
    team = join(db_client, code, "  Red Team  ")
    assert team["teamName"] == "Red Team"
    stored = repo.get_graph(db, team["teamId"])
    assert stored is not None and stored.version == 0 and not stored.locked
    assert stored.graph == default_graph()


def test_session_code_is_case_insensitive(db_client: TestClient) -> None:
    code, _ = create_session(db_client)
    join(db_client, code.lower(), "Blue")


def test_join_unknown_session_is_404(db_client: TestClient) -> None:
    res = db_client.post("/api/sessions/ZZZZZZ/teams", json={"teamName": "Blue"})
    assert res.status_code == 404


@pytest.mark.parametrize("name", ["", "   ", "x" * 31])
def test_team_name_length_is_checked_after_trimming(db_client: TestClient, name: str) -> None:
    code, _ = create_session(db_client)
    res = db_client.post(f"/api/sessions/{code}/teams", json={"teamName": name})
    assert res.status_code == 422


def test_rejoin_by_name_in_another_case_revokes_old_token(db_client: TestClient) -> None:
    code, facilitator = create_session(db_client)
    first = join(db_client, code, "Red Team")
    second = join(db_client, code, "RED team")
    assert second["teamId"] == first["teamId"] and second["teamName"] == "Red Team"
    assert second["token"] != first["token"]

    teams = db_client.get(f"/api/sessions/{code}", headers=bearer(facilitator)).json()["teams"]
    assert len(teams) == 1
    # The old token no longer authenticates; the new one does.
    assert db_client.get(f"/api/sessions/{code}", headers=bearer(first["token"])).status_code == 401
    assert db_client.get(f"/api/sessions/{code}", headers=bearer(second["token"])).status_code == 403


def test_team_limit(db_client: TestClient) -> None:
    code, _ = create_session(db_client)
    for i in range(MAX_TEAMS_PER_SESSION):
        join(db_client, code, f"team {i}")
    res = db_client.post(f"/api/sessions/{code}/teams", json={"teamName": "one too many"})
    assert res.status_code == 409
    # Rejoining an existing team still works in a full session.
    join(db_client, code, "TEAM 0")


def test_same_name_in_another_session_is_another_team(db_client: TestClient) -> None:
    a, _ = create_session(db_client)
    b, _ = create_session(db_client)
    assert join(db_client, a, "Red")["teamId"] != join(db_client, b, "Red")["teamId"]


def test_session_detail_lists_teams_for_facilitator(db_client: TestClient) -> None:
    code, facilitator = create_session(db_client)
    join(db_client, code, "Red")
    join(db_client, code, "Blue")
    res = db_client.get(f"/api/sessions/{code}", headers=bearer(facilitator))
    assert res.status_code == 200
    body = res.json()
    assert body["sessionCode"] == code
    assert [t["name"] for t in body["teams"]] == ["Red", "Blue"]
    assert all(t["graphVersion"] == 0 and t["locked"] is False and t["joinedAt"] for t in body["teams"])


@pytest.mark.parametrize("header", [None, "Bearer", "Basic abc", "Bearer not-a-real-token"])
def test_missing_or_unknown_token_is_401(db_client: TestClient, header: str | None) -> None:
    code, _ = create_session(db_client)
    headers = {"Authorization": header} if header else {}
    res = db_client.get(f"/api/sessions/{code}", headers=headers)
    assert res.status_code == 401
    assert res.headers["www-authenticate"] == "Bearer"


def test_facilitator_token_from_another_session_is_403(db_client: TestClient) -> None:
    code_a, _ = create_session(db_client)
    _, token_b = create_session(db_client)
    assert db_client.get(f"/api/sessions/{code_a}", headers=bearer(token_b)).status_code == 403
    assert db_client.post(f"/api/sessions/{code_a}/lock", json={"locked": True}, headers=bearer(token_b)).status_code == 403


def test_lock_and_unlock_every_team_graph(db_client: TestClient, db: Session) -> None:
    code, facilitator = create_session(db_client)
    other_code, _ = create_session(db_client)
    red = join(db_client, code, "Red")
    join(db_client, code, "Blue")
    outsider = join(db_client, other_code, "Green")

    res = db_client.post(f"/api/sessions/{code}/lock", json={"locked": True}, headers=bearer(facilitator))
    assert res.status_code == 200
    assert all(t["locked"] for t in res.json()["teams"])
    assert repo.get_graph(db, outsider["teamId"]).locked is False

    res = db_client.post(f"/api/sessions/{code}/lock", json={"locked": False}, headers=bearer(facilitator))
    assert not any(t["locked"] for t in res.json()["teams"])
    assert repo.get_graph(db, red["teamId"]).locked is False


def test_tokens_are_never_stored_in_plain_text(db_client: TestClient, db: Session, settings: Settings) -> None:
    code, facilitator = create_session(db_client)
    team = join(db_client, code, "Red")
    session_row = db.scalar(select(SessionRow))
    team_row = db.scalar(select(TeamRow))
    assert session_row.facilitator_token_hash == auth.hash_token(settings.token_secret, facilitator)
    assert team_row.token_hash == auth.hash_token(settings.token_secret, team["token"])
    stored = {session_row.facilitator_token_hash, team_row.token_hash, team_row.name, team_row.name_key}
    assert facilitator not in stored and team["token"] not in stored


def test_current_team_dependency(db_client: TestClient, settings: Settings) -> None:
    """Exercised directly until T13 adds the team endpoints that use it."""
    from fastapi import Depends, FastAPI

    from app.api.deps import current_team
    probe = FastAPI()

    @probe.get("/whoami")
    def whoami(team: TeamRow = Depends(current_team)) -> dict[str, str]:
        return {"teamId": team.id}

    probe.dependency_overrides = app.dependency_overrides
    code, facilitator = create_session(db_client)
    team = join(db_client, code, "Red")
    client = TestClient(probe)
    assert client.get("/whoami", headers=bearer(team["token"])).json() == {"teamId": team["teamId"]}
    assert client.get("/whoami", headers=bearer(facilitator)).status_code == 403
    assert client.get("/whoami").status_code == 401


def test_session_detail_reports_the_session_lock(db_client: TestClient) -> None:
    code, facilitator = create_session(db_client)
    assert db_client.get(f"/api/sessions/{code}", headers=bearer(facilitator)).json()["locked"] is False
    res = db_client.post(f"/api/sessions/{code}/lock", json={"locked": True}, headers=bearer(facilitator))
    assert res.status_code == 200 and res.json()["locked"] is True  # also with no team yet
    res = db_client.post(f"/api/sessions/{code}/lock", json={"locked": False}, headers=bearer(facilitator))
    assert res.json()["locked"] is False


def test_team_joining_after_pencils_down_is_locked(db_client: TestClient) -> None:
    """The M3 open point (Q5): a late team used to start unlocked."""
    code, facilitator = create_session(db_client)
    join(db_client, code, "Red")
    db_client.post(f"/api/sessions/{code}/lock", json={"locked": True}, headers=bearer(facilitator))
    late = join(db_client, code, "Late")
    headers = bearer(late["token"])
    graph = db_client.get(f"/api/teams/{late['teamId']}/graph", headers=headers).json()
    assert graph["locked"] is True
    res = db_client.put(f"/api/teams/{late['teamId']}/graph",
                        json={"graph": graph["graph"], "version": graph["version"]}, headers=headers)
    assert res.status_code == 423
    detail = db_client.post(f"/api/sessions/{code}/lock", json={"locked": False}, headers=bearer(facilitator)).json()
    assert not any(t["locked"] for t in detail["teams"])
