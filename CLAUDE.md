# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

jevVsLLMDemo is an app to show Jev vs LLM usage.

## Pipeline Simulator

Build an interactive AI-pipeline workshop app.

## Stack
- Frontend: React + TypeScript + Vite + React Flow + Zustand
- Backend: Python 3.12 + FastAPI + WebSockets + SQLAlchemy
- Database: SQLite for development; PostgreSQL-compatible models
- Deployment: Vercel for /web, Railway/Render/Fly for /server

## Rules
- Keep frontend and backend in separate folders: web/ and server/.
- Never put API keys in frontend code or commit secrets.
- Use typed models and validation for all graph nodes and edges.
- Build mock Jev and LLM providers before integrating real APIs.
- Write tests for graph validation, node execution, metrics, and WebSocket events.
- Prefer small, reviewable commits.
- Do not add dependencies without explaining why.

## Current status

Scaffolding only — no app features yet.

- `web/`: Vite 6 + React 19 + TypeScript template (unmodified `src/`). React Flow and Zustand are not installed yet. `vite.config.ts` serves on port 5173 and proxies `/api` to `http://localhost:8000`.
- `server/`: FastAPI app in `app/main.py` with only `GET /api/health` and CORS for `http://localhost:5173`. WebSockets, SQLAlchemy, and the graph models are not added yet. Dependencies live in `pyproject.toml` (`dev` extra adds pytest and httpx).
- `.devcontainer/`: Python 3.12 image + Node 20 feature, forwards 5173 and 8000; `postCreateCommand` installs web deps and creates `server/.venv`.

Open question: what a "Jev" node does and which metrics are compared against the LLM is not yet defined — clarify before building providers.

Next planned step: typed graph node/edge models with validation and tests in `server/`.

## Commands

Server (from `server/`):
- Install: `python -m venv .venv && .venv/bin/pip install -e '.[dev]'`
- Run: `.venv/bin/uvicorn app.main:app --reload --port 8000`
- Test: `.venv/bin/pytest`; single test: `.venv/bin/pytest tests/test_health.py::test_health`

Web (from `web/`):
- Install: `npm install`
- Dev server: `npm run dev`
- Build (type-checks via `tsc -b`): `npm run build`
- Lint: `npm run lint`
