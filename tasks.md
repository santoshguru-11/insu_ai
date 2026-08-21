# Tasks

Delivery log for the Autonomous Maintenance Console.

## Done — Task 1: Foundation, backend and database layer

### Repository foundation
- [x] `frontend/` placeholder with a README (no UI code yet)
- [x] `backend/` with a layered package structure
- [x] Root `README.md` documenting every command needed to run the project
- [x] `.gitignore` for Python, Node, virtualenvs, coverage, IDEs, `.env`, logs, builds
- [x] `.env.example` with `APP_ENV`, `APP_NAME`, `LOG_LEVEL`, `DATABASE_URL`,
      `CORS_ORIGINS`, `API_PREFIX` (plus the `POSTGRES_*` values Compose reads)

### FastAPI backend
- [x] Application factory in `backend/app/main.py`
- [x] `GET /health` reporting app status, environment and database connectivity
      (mounted at `/health` and under the `/api/v1` prefix)
- [x] CORS configured for the future Vite dev server on `http://localhost:5173`
- [x] `/api/v1` API prefix, driven by `API_PREFIX`
- [x] Global exception handlers returning the `{"error": {...}}` envelope
- [x] Middleware that reuses `X-Request-ID` or mints a UUID4, and echoes it back
- [x] Structured JSON logs with timestamp, level, request id, method, route,
      status code and duration

### Dependency management
- [x] `uv` with `backend/pyproject.toml` and a committed `backend/uv.lock`
- [x] FastAPI, Uvicorn, SQLAlchemy 2.0 async, asyncpg, Alembic, Pydantic v2,
      pydantic-settings, structlog, pytest, pytest-asyncio, HTTPX, Ruff
- [x] Ruff and pytest configuration in `pyproject.toml`

### PostgreSQL and SQLAlchemy
- [x] `docker-compose.yml` running PostgreSQL 16 only, with a healthcheck
- [x] Data persisted in the named volume `amc_postgres_data`
- [x] Credentials read from the environment; nothing secret in source
- [x] Async engine and `async_sessionmaker`, with a request-scoped session
      dependency that commits on success and rolls back on error
- [x] Models, schemas, repositories and services kept in separate packages

### Alembic
- [x] Async Alembic environment under `backend/alembic/`
- [x] Autogenerate wired to `Base.metadata`; URL comes from the environment
- [x] Initial migration created, applied, and verified reversible (up/down/up)
- [x] `uv run alembic check` reports no drift between models and migrations

### Schema
- [x] All 11 tables with UUID primary keys and timestamp columns
- [x] Native PostgreSQL enums for every status/classification column
- [x] Check constraints on confidence ranges, durations, quantities, RUL bounds
- [x] Indexes on incident workflow status, asset id, trace id, event occurrence
      time, incident detection time, and approval decision/status
- [x] `audit_events` append-only: no mutating repository methods, plus the
      `trg_audit_events_append_only` database trigger

### Tests
- [x] `GET /health` succeeds and reports database connectivity
- [x] Request ids are generated, preserved when supplied, and returned
- [x] The initial migration creates every expected table, index and constraint
- [x] Audit events cannot be updated or deleted (database and repository level)
- [x] Structured log lines carry the required fields
- [x] Settings parsing and CORS behaviour
- [x] 28 tests, all passing; `ruff check` clean

## Done — Task 2: Simulated workflow, APIs, approval and realtime

### Pydantic contracts
- [x] Asset, incident list item, incident detail, agent run, diagnosis,
      diagnosis alternative, evidence item, RUL estimate, maintenance proposal,
      part check, approval request/decision, work order, technician outcome,
      audit event, WebSocket event, simulate-next-step request/response
- [x] UUIDs and UTC ISO-8601 timestamps throughout
- [x] Enums for every state, severity, confidence and decision field

### Workflow
- [x] Nine states: watch, escalated, diagnosed, human_review, approval_required,
      approved, rejected, work_order_live, resolved
- [x] Dedicated `WorkflowService`; no transition logic in route handlers
- [x] Exactly the ten specified transitions; anything else returns
      `INVALID_WORKFLOW_TRANSITION` with the reachable states
- [x] Idempotent: re-requesting the current state is a no-op with no audit event
- [x] Every transition audits previous state, next state, actor, reason,
      trace id, timestamp and payload
- [x] Approval only accepted in `approval_required`
- [x] No reservation or work order before an approval decision exists

### Database
- [x] `diagnosis_alternatives` and `sentinel_anomalies` tables
- [x] `incidents.scenario_type`, `cloud_available`, `human_review_reason`
- [x] `approval_decisions.token_id`, `token_hash`, `token_expires_at`, `used_at`
- [x] Workflow and severity enums rebuilt; migration verified reversible
- [x] `audit_events` remains append-only

### Seed
- [x] `uv run python -m app.seed.demo` (`--reset`), idempotent on
      `asset_code` and `trace_id`
- [x] Scenario A `tr_9f21` / CAL-04-DRIVE in `approval_required`
- [x] Scenario B `tr_5c07` in `human_review`, confidence 0.52, two plausible modes
- [x] Scenario C `tr_1d88` with `cloud_available = false`

### API
- [x] Assets list/detail with filters; incidents list/detail with filters
- [x] Audit timeline, approve, reject, simulate-next-step, outcome
- [x] `WS /ws/incidents/{incident_id}` with snapshot and broadcasts
- [x] Tags, summaries and response models on every route; `/docs` renders all ten

### Tests
- [x] 75 tests passing, `ruff check` and `ruff format` clean
- [x] Asset listing, incident listing/filtering, full detail, audit timeline
- [x] Valid approval, invalid approval state, rejection
- [x] Low-confidence cannot auto-advance; offline blocks cloud actions
- [x] Outcome capture; invalid workflow transition
- [x] WebSocket update received after approval
- [x] Audit events exist for every workflow transition

## Next

### Task 3 — Domain API surface
- [ ] Write endpoints for assets and incidents (today: read plus workflow actions)
- [ ] Sorting conventions and cursor pagination for large result sets
- [ ] Repositories for the remaining child tables

### Task 4 — React frontend
- [ ] Vite + React + TypeScript scaffold in `frontend/`
- [ ] Incident list and detail views with the diagnosis evidence trail
- [ ] Approval screen and the audit timeline

### Task 5 — Scaling and integrations
- [ ] Replace the in-memory WebSocket manager with Redis pub/sub or NATS
- [ ] Verify a presented approval token against its stored hash on redemption

### Task 6 — Integrations (explicitly out of scope until then)
- [ ] Authentication and authorisation
- [ ] LLM / MCP diagnostic agents
- [ ] Litmus / MES / ERP / CMMS connectors
- [ ] Teams notifications
- [ ] Live telemetry ingestion
