"""Tables: sessions, teams, graphs (M3, decision P4), runs (M4, decision Q8) and provider_calls
(MVP step 2, U3). Request traces stay in memory until M5."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, new_id, utcnow


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(6), unique=True)
    facilitator_token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    # Pencils down (Q5). Graph rows keep their own flag in step; this one also locks teams that
    # join afterwards.
    locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class TeamRow(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("session_id", "name_key", name="uq_teams_session_id_name_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(30))
    name_key: Mapped[str] = mapped_column(String(30))  # casefolded name, unique per session
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class GraphRow(Base):
    __tablename__ = "graphs"

    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON)  # Graph in its wire format (camelCase)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class RunRow(Base):
    """One practice or official run of a team's graph snapshot (Q8)."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(16))  # RunMode
    status: Mapped[str] = mapped_column(String(16))  # RunStatus
    config: Mapped[dict[str, Any]] = mapped_column(JSON)  # RunConfig, wire format
    graph: Mapped[dict[str, Any]] = mapped_column(JSON)  # the snapshot that ran, wire format
    graph_version: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # RunMetrics once finished
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ProviderCallRow(Base):
    """One real (live) provider call, kept so identical requests replay it (U3).

    The key is a hash of the provider, the model and the exact request fields; no request body is
    stored. Latency is the measured one, so a replay keeps the original timing (U4). The sum of
    cost_usd since midnight UTC is the day's real spend (U10).
    """

    __tablename__ = "provider_calls"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))  # "jev" | "gemini" | "claude"
    model: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    latency_ms: Mapped[float] = mapped_column(Float)
    tokens_in: Mapped[int] = mapped_column(Integer)
    tokens_out: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
