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
Scaffolding plus T1 (domain models), T2 (node catalog), T3 (graph validator), T4 (scenario packs, mock providers, tools, runners) and T5 (executor, metrics, scoring, headless runs). M1's headless engine is complete. Endpoints: health, catalog, default graph, validate.

T2 is committed (`fceba65`); its changes and the design decisions still to review are listed in `specs-and-plans/t2new.txt`. T3 is committed (`3e138c4`) and pushed to `origin/open-terminal`. T4 is committed as five commits starting at `d8f06a0` (subjects begin "T4:") and pushed; its plan, accepted decisions and as-built notes are in `specs-and-plans/t4-plan.txt`. T5 is committed as four commits (subjects begin "T5:") and pushed; see `specs-and-plans/t5-plan.txt` (decisions, tuning results). `claude1.md` is an old snapshot of this file kept for reference only; this file is the current one. `server/scratch.py` is a local manual-check script; it is git-ignored, do not commit it.

- `server/app/models/` (T1 done): Pydantic v2 domain types from plan1.txt §2a — `ports.py` (PortType, Port), `params.py` (ParamSpec union discriminated on `kind`; each spec has `check(value)`), `catalog.py` (NodeDefinition, CostModel; self-consistency validated), `graph.py` (Graph ≤40 nodes/≤80 edges, GraphNode, GraphEdge, StoredGraph), `values.py` (PortValue + Taint, Distribution), `results.py` (NodeResult, NodeError), `validation.py` (IssueCode, ValidationIssue, ValidationReport). All inherit `CamelModel` (`base.py`): camelCase on the wire (`model_dump(by_alias=True)`), snake_case in Python, unknown fields rejected. Run/metrics/event models are deferred to T5.
- `server/app/catalog/` (T2 done): `definitions/{io,jev,llm,tool,human}.py` hold the 7 MVP `NodeDefinition`s (metadata + CostModel). `registry.py` maps type → (definition, `StubRunner` that raises `NotImplementedError`) and has `resolve_params` (defaults + checks) and `expand_outputs` (expands a dynamic template port like `route.*` into `route.<value>` per selected param value). `default_graph.py` builds the intentionally imperfect starter graph; `shared/fixtures/graphs/default.json` is generated from it (`python -m app.catalog.default_graph`) and a test fails if they drift.
- `server/app/api/`: `catalog.py` (`GET /api/catalog` → `{"nodes": [...]}`, dynamic ports left as templates) and `graphs.py` (`GET /api/graphs/default`, `POST /api/graphs/validate`).
- `server/app/engine/` (T3 done): `planner.py` holds pure graph functions (deterministic topological order, Tarjan `find_cycles`, `reachable`, `branch_conditions` and `mutually_exclusive` for exclusive branches); T5's executor reuses it. `validator.py` has `validate_graph(graph, definitions=None)` (every IssueCode from plan1.txt §3d; checks continue after errors but only resolved nodes/edges feed later checks) and `validate_payload(raw)`, which reports GRAPH_TOO_LARGE before parsing. `POST /api/graphs/validate` is stateless and returns a ValidationReport. `NodeDefinition.requires_one_of` drives GATE_NEEDS_SIGNAL. Fixtures: `shared/fixtures/graphs/invalid-<code>.json`, one per error code that the MVP catalog can produce; ENUM_VALUES_MISMATCH, GATE_NEEDS_SIGNAL and ANY_SOURCE are tested with test-only definitions. The default graph gives exactly 2× UNCONNECTED_BRANCH + NO_HUMAN_FALLBACK. Change summary: `specs-and-plans/t3-change-summary.txt`.
- T4 (done): `app/models/scenarios.py` (Ticket with `risk` and `pii_kinds`, ScoringConfig, ScenarioPack, PackSummary) and `payloads.py` (json port payloads: TicketMeta, Docs, PolicyReport). `app/simulation/packs/{practice,official}.json` (15 and 30 tickets) loaded by `simulation/loader.py` (`load_pack`, `pack_summary` hides the official pack). `app/engine/seeding.py` (sha256 seed over run seed, ticket, node type, provider-relevant params and input fingerprint; never the router threshold), `latency.py` (lognormal), `envelope.py` (RequestEnvelope, RunContext, `make_context` with mock providers). `app/providers/base.py` (JevProvider/LLMProvider protocols) with `mock_jev.py` and `mock_llm.py`. `app/tools/` (`pii.py`, `policy.py`, `knowledge.py` + `kb.json`): pure functions. `app/runners/` holds one runner per node type and the `NodeRunner` protocol; `registry.py` maps types to them. `knowledge_lookup` is the 8th catalog node. `app/config.py` holds placeholder LLM prices. Taint rides on text values; each mock marker phrase is caught by exactly one policy rule.
- T5 (done): `app/models/runs.py` (RunConfig, NodeExecution, RequestTrace, RunSummary), `metrics.py` (NodeStats, RunMetrics, LeaderboardRow), `events.py` (ServerEvent union discriminated on `type`, ClientMessage). `app/engine/executor.py`: `ExecutionPlan.build(graph)` (raises `InvalidGraphError` on validation errors) and `execute_request` (dead-path elimination, earliest-arrival multi inputs, critical-path latency, outcome/released_unsafe/decision_correct; events come back unnumbered). `app/engine/events.py` (EventSink, InMemorySink). `app/metrics/aggregator.py` (nearest-rank percentiles, rates, node stats), `app/simulation/scoring.py`, `traffic.py` (seeded arrival schedule, spike, injection wave), `runner.py` (`run_simulation` merges every request's events by sim time, inserts throttled metrics snapshots, numbers them), `reference_graphs.py` (default/weak/strong/escalate_all builders; `python -m app.simulation.reference_graphs` regenerates `shared/fixtures/graphs/{weak,strong}.json`). Pack cost budget is $1000 per 1k requests (human review dominates cost).
- `server/app/catalog/compat.py`: `type_compat` (ok/warn/blocked) and `port_compat` (adds IssueCode + enum-subset check). The rules are pinned by `shared/fixtures/port-compat-cases.json` (all 64 type pairs); the future TS mirror must pass the same fixture.
- `web/`: Vite 6 + React 19 + TypeScript template (unmodified `src/`). React Flow and Zustand are not installed yet. `vite.config.ts` serves on port 5173 and proxies `/api` to `http://localhost:8000`.
- `server/`: FastAPI app in `app/main.py` (CORS for `http://localhost:5173`, includes the `app/api/` routers). WebSockets and SQLAlchemy are not added yet. Dependencies live in `pyproject.toml` (`dev` extra adds pytest and httpx).
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

Next planned step: M2 — schema export (`scripts/export_schema.py` → `shared/schema/`), TS codegen, then the React Flow canvas. Then persistence and first deployment (M3) and live runs over WebSockets (M4).

## Commands

Server (from `server/`):
- Install: `python -m venv .venv && .venv/bin/pip install -e '.[dev]'`
- Run: `.venv/bin/uvicorn app.main:app --reload --port 8000`
- Headless run: `.venv/bin/python scripts/run_headless.py <default|weak|strong|escalate_all|path.json> <practice|official> [--seed N | --seeds N] [--json]`
- Test: `.venv/bin/pytest`; single test: `.venv/bin/pytest tests/test_health.py::test_health`
- Tests: `test_health.py` (health endpoint), `test_models.py` (wire format, ports, params, node definitions, graphs, results), `test_compat.py` (fixture-driven), `test_catalog.py` (catalog consistency, params, branch expansion, default graph, endpoints), `test_planner.py` (topo order, cycles, branch exclusivity), `test_validator.py` (one case per IssueCode, default-graph warnings, validate endpoint), `test_packs.py` (pack mix and label consistency), `test_tools.py` (table-driven PII, policy, knowledge lookup) `test_runners.py` (seeding, output contracts for every runner × ticket, determinism, threshold monotonicity, mock rates), `test_executor.py` (dead paths, multi inputs, critical path, outcome truth table, determinism), `test_events.py` (event-order invariants), `test_metrics.py`, `test_simulation.py` (traffic, runner, reference fixtures, headless script) and `test_golden.py` (default/weak/strong/escalate_all separate on 10 seeds). Tests import `app.*` and read `shared/fixtures/` relative to the repo root.

Web (from `web/`):
- Install: `npm install`
- Dev server: `npm run dev`
- Build (type-checks via `tsc -b`): `npm run build`
- Lint: `npm run lint`
