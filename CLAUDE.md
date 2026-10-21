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

Scaffolding plus T1 (domain models) — no app features or endpoints yet beyond health.

- `server/app/models/` (T1 done): Pydantic v2 domain types from plan1.txt §2a — `ports.py` (PortType, Port), `params.py` (ParamSpec union discriminated on `kind`; each spec has `check(value)`), `catalog.py` (NodeDefinition, CostModel; self-consistency validated), `graph.py` (Graph ≤40 nodes/≤80 edges, GraphNode, GraphEdge, StoredGraph), `values.py` (PortValue + Taint, Distribution), `results.py` (NodeResult, NodeError), `validation.py` (IssueCode, ValidationIssue, ValidationReport). All inherit `CamelModel` (`base.py`): camelCase on the wire (`model_dump(by_alias=True)`), snake_case in Python, unknown fields rejected. Run/metrics/event models are deferred to T5.
- `server/app/catalog/compat.py`: `type_compat` (ok/warn/blocked) and `port_compat` (adds IssueCode + enum-subset check). The rules are pinned by `shared/fixtures/port-compat-cases.json` (all 64 type pairs); the future TS mirror must pass the same fixture.
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

Next planned step: T2 — MVP node catalog (7 node definitions), registry with dynamic branch-port expansion, default starter graph, and `GET /api/catalog`. Then T3–T5 (validator, mocks/runners, executor/metrics) to reach a headless engine before building the canvas.

## Commands

Server (from `server/`):
- Install: `python -m venv .venv && .venv/bin/pip install -e '.[dev]'`
- Run: `.venv/bin/uvicorn app.main:app --reload --port 8000`
- Test: `.venv/bin/pytest`; single test: `.venv/bin/pytest tests/test_health.py::test_health`
- Tests: `test_models.py` (wire format, ports, params, node definitions, graphs, results) and `test_compat.py` (fixture-driven). Tests import `app.*` and read `shared/fixtures/` relative to the repo root.

Web (from `web/`):
- Install: `npm install`
- Dev server: `npm run dev`
- Build (type-checks via `tsc -b`): `npm run build`
- Lint: `npm run lint`
