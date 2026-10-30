"""M3 tables (decision P4): sessions, teams, graphs. Run tables arrive with M4/M5."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, new_id, utcnow


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(6), unique=True)
    facilitator_token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


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
