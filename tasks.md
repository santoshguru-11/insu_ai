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

## Next

### Task 2 — Domain API surface
- [ ] CRUD endpoints for assets and incidents
- [ ] Read endpoints for diagnoses, evidence, proposals and work orders
- [ ] Pagination, filtering and sorting conventions
- [ ] Repositories and services for the remaining tables
- [ ] Audit events emitted on every state transition

### Task 3 — Approval workflow
- [ ] Proposal submission and the approval state machine
- [ ] Single-use approval tokens with expiry (hash comparison only)
- [ ] Enforce that irreversible actions require a recorded approval

### Task 4 — React frontend
- [ ] Vite + React + TypeScript scaffold in `frontend/`
- [ ] Incident list and detail views with the diagnosis evidence trail
- [ ] Approval screen and the audit timeline

### Task 5 — Integrations (explicitly out of scope until then)
- [ ] Authentication and authorisation
- [ ] LLM / MCP diagnostic agents
- [ ] Litmus / MES / ERP / CMMS connectors
- [ ] Teams notifications
- [ ] Live telemetry ingestion
