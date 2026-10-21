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

## Spec and plan

- Spec: `specs-and-plans/pipeline-simulator-spec.pdf`. Jev nodes make bounded, typed decisions (choice/score/boolean + confidence); LLM nodes generate text; tools are deterministic; human review handles uncertain/risky cases. Metrics: automation rate, escalation rate, unsafe-release rate, p50/p95 latency, cost per 1k requests, decision quality.
- Implementation plan: `specs-and-plans/plan1.txt` — folder structure, shared types, node catalog/port contracts, milestones M1–M7, test plan, deployment, and tasks T1–T5. Follow it; update it when a decision changes.

Key architecture decisions (details in plan1.txt §0):
- Server owns all node logic; the browser gets the catalog as metadata from `GET /api/catalog` and never runs nodes or sees the hidden scenario pack.
- Pydantic models are the source of truth; JSON Schema is exported to `shared/schema/` and TS types are generated into `web/src/types/generated.ts` (do not edit by hand). Port-compat logic is mirrored in TS and tested against `shared/fixtures/port-compat-cases.json`.
- Control flow uses exclusive branch output ports (e.g. `route.billing`); nodes on unfired branches are skipped.
- Mocks are deterministic: seed = sha256(run_seed, scenario_id, node_type, params) — never Python `hash()`.
- Single backend instance (in-memory run state + WebSocket hub); one graph per team, last-write-wins with version (409 stale, 423 locked).

Next planned step: T1 — domain models and port compatibility in `server/app/models/` and `server/app/catalog/compat.py`, with tests. Then T2–T5 (catalog, validator, mocks/runners, executor/metrics) to reach a headless engine before building the canvas.

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
