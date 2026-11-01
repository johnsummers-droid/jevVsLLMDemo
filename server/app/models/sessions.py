"""Wire models for workshop sessions, teams and facilitator actions (T12)."""

from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from app.models.base import CamelModel

MAX_TEAMS_PER_SESSION = 12

# Trimmed before the length check, so "  " is rejected like "".
TeamName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


class CreateSessionRequest(CamelModel):
    facilitator_code: str


class CreateSessionResponse(CamelModel):
    session_code: str
    facilitator_token: str


class JoinTeamRequest(CamelModel):
    team_name: TeamName


class JoinTeamResponse(CamelModel):
    team_id: str
    team_name: str
    token: str


class TeamSummary(CamelModel):
    team_id: str
    name: str
    joined_at: datetime
    graph_version: int = Field(ge=0)
    locked: bool


class SessionDetail(CamelModel):
    session_code: str
    created_at: datetime
    locked: bool  # pencils down: every graph, including those of teams that join later
    teams: list[TeamSummary]


class LockRequest(CamelModel):
    locked: bool


class ReferenceGraphInfo(CamelModel):
    name: str
    label: str


class ReferenceGraphList(CamelModel):
    """Which reference graphs the caller may view; empty for a team until the reveal (T40)."""

    available: bool
    graphs: list[ReferenceGraphInfo]
