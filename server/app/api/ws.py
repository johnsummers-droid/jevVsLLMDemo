"""GET /api/ws: the live event stream (T19, decisions Q2-Q4).

The client authenticates with its FIRST message, {"type": "auth", "token": ...}, so the bearer
token never appears in a URL (uvicorn and Render log URLs). The first event it receives is
state_sync. Close codes: 4401 no or bad auth, 4403 token revoked by a rejoin, 1013 too slow,
1011 server not configured. Every server-side close is preceded by a `closing` event carrying the
same code, because Render's proxy does not pass close frames on to the client. After auth, a
{"type": "ping"} is answered with {"type": "pong"}: the client's heartbeat (models.events.Pong).
"""

import asyncio
from collections.abc import Awaitable

import anyio
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app import auth
from app.config import Settings, get_settings
from app.db import repo
from app.db.session import get_db
from app.models.events import Auth, ClientMessage, Closing, Ping, Pong
from app.realtime.hub import Connection, hub

router = APIRouter(tags=["realtime"])

AUTH_TIMEOUT_S = 5.0
CLOSE_AUTH = 4401
CLOSE_UNCONFIGURED = 1011

_messages: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def _identify(db: Session, secret: str, token: str) -> tuple[Connection, bool] | None:
    """The socket's channel and lock state for a team or facilitator token, or None."""
    token_hash = auth.hash_token(secret, token)
    try:
        team = repo.get_team_by_token_hash(db, token_hash)
        if team is not None:
            stored = repo.get_graph(db, team.id)
            return Connection(team.session_id, team.id), bool(stored and stored.locked)
        session = repo.get_session_by_facilitator_hash(db, token_hash)
        if session is not None:
            return Connection(session.id, None), session.locked
        return None
    finally:
        db.rollback()  # hand the connection back: the socket may stay open for an hour


async def _first_message(websocket: WebSocket) -> Auth | None:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), AUTH_TIMEOUT_S)
        message = _messages.validate_json(raw)
    except (TimeoutError, ValidationError, KeyError):
        return None
    return message if isinstance(message, Auth) else None


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    """`closing` first: Render's proxy swallows the close frame (models.events.Closing)."""
    try:
        await websocket.send_text(Closing(seq=0, sim_ms=0, code=code, reason=reason).model_dump_json(by_alias=True))
        await websocket.close(code, reason)
    except (WebSocketDisconnect, RuntimeError):  # the client went away first
        pass


async def _write(websocket: WebSocket, conn: Connection) -> None:
    """Sends queued events until the hub closes the connection (or the client goes away)."""
    try:
        while (event := await conn.queue.get()) is not None:
            await websocket.send_text(event.model_dump_json(by_alias=True))
    except (WebSocketDisconnect, RuntimeError):
        pass


async def _read(websocket: WebSocket, conn: Connection) -> None:
    """Answers pings with a pong (through the socket's queue, so it stays in order with events);
    anything else a client sends after auth is ignored (Q3). Returns on disconnect."""
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = _messages.validate_json(raw)
            except ValidationError:
                continue
            if isinstance(message, Ping):
                conn.send(Pong(seq=0, sim_ms=0, team_id=conn.team_id))
    except WebSocketDisconnect:
        pass


@router.websocket("/api/ws")
async def events_socket(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> None:
    await websocket.accept()
    if not settings.token_secret:
        await _close(websocket, CLOSE_UNCONFIGURED, "TOKEN_SECRET is not configured")
        return
    try:
        message = await _first_message(websocket)
    except WebSocketDisconnect:
        return
    found = await run_in_threadpool(_identify, db, settings.token_secret, message.token) if message else None
    if found is None:
        await _close(websocket, CLOSE_AUTH, "authenticate with a valid token first")
        return
    conn, locked = found
    hub.connect(conn, locked)
    try:
        async with anyio.create_task_group() as tasks:
            async def until_either_ends(half: Awaitable[None]) -> None:
                await half
                tasks.cancel_scope.cancel()  # the other half stops too

            tasks.start_soon(until_either_ends, _write(websocket, conn))
            tasks.start_soon(until_either_ends, _read(websocket, conn))
    finally:
        hub.disconnect(conn)
    if conn.close_code is not None:
        try:
            await websocket.close(conn.close_code)
        except RuntimeError:  # the client went away first
            pass
