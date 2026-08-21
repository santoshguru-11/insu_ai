# Autonomous Maintenance Console

Industrial predictive-maintenance console. Machine anomalies are detected,
diagnosed by agents, turned into maintenance proposals, gated behind explicit
human approval before anything irreversible happens, dispatched as work orders,
and closed out with technician findings — with a complete, append-only audit
trail behind all of it.

This repository contains the **backend**: FastAPI application, PostgreSQL
schema, migrations, a simulated agent workflow with demo data, the REST API,
the human approval gate, and realtime WebSocket updates. The React frontend has
not been built yet (`frontend/` is a placeholder).

The agents and enterprise systems are **simulated** — the code makes no LLM,
MCP, Litmus, MES, ERP, CMMS or Teams calls, and ingests no live telemetry.

---

## Prerequisites

| Tool           | Version | Notes                                                   |
| -------------- | ------- | ------------------------------------------------------- |
| Python         | 3.12+   | `uv` can install it for you (`uv python install 3.12`)  |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | Dependency manager and task runner |
| Docker         | 24+     | With the Compose v2 plugin, for local PostgreSQL         |
| PostgreSQL     | 13+     | Provided by Docker Compose; 13+ for `gen_random_uuid()`  |

---

## Setup

```bash
# 1. Clone and enter the repository
git clone https://github.com/santoshguru-11/insu_ai.git
cd insu_ai

# 2. Create your local environment file and set a database password
cp .env.example .env
$EDITOR .env          # replace every `change-me-locally` value

# 3. Install backend dependencies (creates backend/.venv from uv.lock)
cd backend && uv sync && cd ..
```

`.env` is git-ignored. No credentials are committed anywhere in this repository;
`docker-compose.yml`, `alembic.ini`, and the application all read them from the
environment.

---

## Commands

Every backend command runs from the `backend/` directory.

### Start the database

```bash
docker compose up -d              # from the repository root
docker compose ps                 # confirm the container is healthy
docker compose logs -f postgres   # follow logs
docker compose down               # stop (data survives in the named volume)
docker compose down -v            # stop AND delete the data volume
```

Data lives in the named Docker volume `amc_postgres_data`, so it survives
container restarts.

### Apply migrations

```bash
cd backend
uv run alembic upgrade head
```

### Seed the demo data

```bash
cd backend
uv run python -m app.seed.demo           # create or refresh the three scenarios
uv run python -m app.seed.demo --reset   # delete them first, then recreate
```

The seed is idempotent — keyed on `asset_code` and `trace_id`, so running it
repeatedly replaces each scenario in place instead of stacking duplicates. It
does **not** delete audit events: the trail is append-only by design, so a reset
adds to the history rather than erasing it.

| Scenario | Trace | Asset | State | What it demonstrates |
| -------- | ----- | ----- | ----- | -------------------- |
| A | `tr_9f21` | `CAL-04-DRIVE` | `approval_required` | The main approval walkthrough |
| B | `tr_5c07` | `MIX-02-AGITATOR` | `human_review` | Low confidence cannot auto-advance |
| C | `tr_1d88` | `COAT-01-DRYER` | `diagnosed` | WAN loss blocks cloud actions |

### Run the API

```bash
cd backend
uv run uvicorn app.main:app --reload
```

| URL                                    | What it is                       |
| -------------------------------------- | -------------------------------- |
| http://localhost:8000/health           | Health check                     |
| http://localhost:8000/api/v1/health    | Same check under the API prefix  |
| http://localhost:8000/docs             | Swagger UI                       |
| http://localhost:8000/redoc            | ReDoc                            |
| http://localhost:8000/openapi.json     | OpenAPI schema                   |
| `ws://localhost:8000/ws/incidents/{id}`| Realtime incident channel        |

### Run the tests

```bash
cd backend
uv run pytest                     # whole suite
uv run pytest -m db               # only the database-backed tests
uv run pytest -m "not db"         # skip anything needing PostgreSQL
uv run pytest -vv                 # verbose
```

Database tests build a scratch database named after your configured one with a
`_test` suffix (e.g. `amc_test`), run the real migrations against it, and drop
it at the start of the next run. Override the target with `TEST_DATABASE_URL`.
When no PostgreSQL server is reachable those tests are **skipped**, not failed.

### Lint and format

```bash
cd backend
uv run ruff check .               # lint
uv run ruff check . --fix         # lint and autofix
uv run ruff format .              # format
uv run ruff format --check .      # verify formatting in CI
```

### Working with migrations

```bash
cd backend

# Generate a new migration after changing anything under app/models/
uv run alembic revision --autogenerate -m "add technician skill matrix"

# Apply / roll back
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic downgrade base

# Inspect
uv run alembic current            # revision the database is on
uv run alembic history --verbose  # full revision history
uv run alembic check              # fail if models have drifted from migrations
```

Always read the generated file before committing it — autogenerate does not
detect every change (renames, data migrations, triggers, and check constraints
usually need a hand-written step).

### From zero to a running stack

```bash
cp .env.example .env && $EDITOR .env
docker compose up -d
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.seed.demo
uv run pytest
uv run ruff check .
uv run uvicorn app.main:app --reload
```

---

## Workflow

```
sentinel -> diagnosis -> planner -> parts check -> HUMAN APPROVAL
         -> part reservation + work order -> technician outcome -> resolved
```

States and the only legal moves between them:

| From | To | When |
| ---- | -- | ---- |
| `watch` | `escalated` | The sentinel anomaly persists across analysis windows |
| `escalated` | `diagnosed` | The diagnosis agent finishes |
| `diagnosed` | `human_review` | Confidence is low or evidence is insufficient |
| `diagnosed` | `approval_required` | Confidence is medium/high and the action is not `monitor` |
| `human_review` | `approval_required` | A human escalates the case |
| `approval_required` | `approved` | A human approves |
| `approval_required` | `rejected` | A human rejects |
| `approved` | `work_order_live` | The work order is dispatched |
| `work_order_live` | `resolved` | The technician reports the outcome |
| `rejected` | `watch` | The asset goes back under sentinel watch |

**The core rule:** no irreversible action — part reservation or work-order
creation — happens before a valid approval decision. `POST /approve` performs
them in a fixed order, each with its own audit event, so the trail proves the
approval came first:

```
approval.created -> workflow.transitioned(approval_required -> approved)
  -> part.reserved -> work_order.created
  -> workflow.transitioned(approved -> work_order_live)
```

Anything else is refused. `simulate-next-step` stops dead at
`approval_required`; approving an incident in any other state returns
`APPROVAL_NOT_REQUIRED`; an illegal transition returns
`INVALID_WORKFLOW_TRANSITION` listing the states that *are* reachable.

All transition logic lives in `app/services/workflow.py`, never in a route
handler, and every state change writes an `audit_events` row carrying the
previous state, next state, actor, reason, trace id, timestamp and payload.

---

## API

Routes below omit the configured `API_PREFIX` (`/api/v1`).

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/assets` | Paginated assets; filters: `criticality`, `status`, `plant_name` |
| `GET` | `/assets/{asset_id}` | Asset detail plus latest incident summary |
| `GET` | `/incidents` | Paginated incidents; filters: `workflow_status`, `severity`, `asset_id`, `scenario_type` |
| `GET` | `/incidents/{incident_id}` | Full incident detail |
| `GET` | `/incidents/{incident_id}/audit` | Paginated audit timeline, oldest first |
| `POST` | `/incidents/{incident_id}/approve` | Approve, reserve parts, create work order `WO-40219` |
| `POST` | `/incidents/{incident_id}/reject` | Reject, return to `watch`, reserve nothing |
| `POST` | `/incidents/{incident_id}/simulate-next-step` | Advance the guided demo one legal step |
| `POST` | `/incidents/{incident_id}/outcome` | Capture the technician outcome and resolve |
| `WS` | `/ws/incidents/{incident_id}` | Realtime incident channel (not versioned) |

### Approval tokens

Approving mints a scoped, single-use token. Only its id and a SHA-256 hash are
stored; the raw secret is never persisted and never returned. The response
carries `token_id`, `expires_at` (15 minutes) and `scope`
(`incident:<id>:approve`), which is what an auditor needs to tie the
irreversible actions to one decision.

### Realtime events

The socket sends `incident.snapshot` on connect, then one envelope per change:

```json
{
  "event_type": "incident.updated",
  "incident_id": "uuid",
  "trace_id": "tr_9f21",
  "occurred_at": "2026-08-21T07:33:21.161778Z",
  "data": {}
}
```

Event types: `incident.snapshot`, `incident.updated`, `approval.created`,
`approval.rejected`, `part.reserved`, `work_order.created`, `outcome.captured`.

Fan-out is an in-memory connection manager (`app/realtime/manager.py`), which
only reaches clients attached to *this* process. Running more than one backend
instance requires a shared bus — Redis pub/sub, NATS, or Postgres
`LISTEN/NOTIFY` — with each instance relaying to its own sockets. The
publish/subscribe surface is kept narrow so that swap touches one file.

### Cloud-unavailable behaviour

An incident with `cloud_available = false` keeps its sentinel anomaly and
diagnosis readable, but every cloud-dependent action (planner, parts, approval,
reservation, work-order creation) returns `503 CLOUD_UNAVAILABLE`. The refusal
is written to the audit trail on its own transaction, so it survives the
rollback of the request that triggered it.

---

## Configuration

All settings come from the environment; see `.env.example` for the full list.

| Variable        | Purpose                                            | Example                                                   |
| --------------- | -------------------------------------------------- | --------------------------------------------------------- |
| `APP_ENV`       | Deployment environment                              | `local`                                                    |
| `APP_NAME`      | Name reported in logs and `/health`                 | `Autonomous Maintenance Console`                           |
| `LOG_LEVEL`     | Root log level                                      | `INFO`                                                     |
| `DATABASE_URL`  | Async SQLAlchemy DSN (asyncpg driver)               | `postgresql+asyncpg://amc:...@localhost:5432/amc`          |
| `CORS_ORIGINS`  | Comma-separated allowed browser origins             | `http://localhost:5173`                                    |
| `API_PREFIX`    | Prefix for versioned routes                         | `/api/v1`                                                  |

`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `POSTGRES_PORT` are
read by `docker-compose.yml` and must agree with `DATABASE_URL`.

---

## Project layout

```
.
├── frontend/              # placeholder for the React UI (not built yet)
├── backend/
│   ├── app/
│   │   ├── api/           # routers + FastAPI dependencies
│   │   ├── core/          # settings, logging, middleware, error handling
│   │   ├── db/            # declarative base, async engine, session dependency
│   │   ├── models/        # SQLAlchemy models — the source for migrations
│   │   ├── schemas/       # Pydantic request/response models
│   │   ├── repositories/  # all SQL lives here
│   │   ├── services/      # workflow, approval, simulation, outcome
│   │   ├── realtime/      # in-memory WebSocket connection manager
│   │   ├── seed/          # demo scenarios and the seed command
│   │   └── main.py        # application factory
│   ├── alembic/           # migration environment and revisions
│   ├── tests/
│   ├── alembic.ini
│   └── pyproject.toml
├── docker-compose.yml     # PostgreSQL only
├── .env.example
└── tasks.md               # delivery status and what comes next
```

Layers only ever call downward: `api → services → repositories → models`.
Route handlers never build queries themselves.

---

## API conventions

### Request IDs

Every request is assigned an id: the incoming `X-Request-ID` header is reused
when present, otherwise a UUID4 is generated. It comes back on the response as
`X-Request-ID`, appears in every log line for that request, and is included in
every error body.

### Errors

Failures always return the same envelope:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "The requested resource was not found.",
    "request_id": "9c1f...",
    "details": {}
  }
}
```

### Logging

Logs are newline-delimited JSON on stdout, ready to ship to any collector:

```json
{"request_id": "9c1f...", "method": "GET", "route": "/api/v1/health",
 "status_code": 200, "duration_ms": 3.14, "event": "http_request",
 "level": "info", "logger": "app.access", "timestamp": "2026-08-21T06:54:47Z"}
```

---

## Data model

| Table                   | What it holds                                              |
| ----------------------- | ---------------------------------------------------------- |
| `assets`                | Monitored equipment, keyed by `asset_code` (`CAL-04-DRIVE`) |
| `incidents`             | A detected anomaly, tracked through the workflow            |
| `sentinel_anomalies`    | The raw deviation that opened the incident                  |
| `agent_runs`            | One execution of a diagnostic agent                         |
| `diagnoses`             | Failure mode, confidence, recommended action, RUL estimate  |
| `evidence_items`        | Signals cited in support of a diagnosis                     |
| `diagnosis_alternatives`| Failure modes considered and ruled out, with the reasoning  |
| `maintenance_proposals` | Proposed window, duration, production impact                |
| `part_checks`           | Spare-part availability behind a proposal                   |
| `approval_decisions`    | The human approval gate, with a hashed single-use token     |
| `work_orders`           | Work dispatched after approval                              |
| `technician_outcomes`   | Ground truth from the shop floor                            |
| `audit_events`          | Append-only trail, correlated by `trace_id`                 |

Every table uses a UUID primary key generated by the database, plus
`created_at` (and `updated_at` where the row is mutable).

### The audit trail is append-only

`audit_events` can be inserted into and read, never modified:

1. `AuditEventRepository` extends a read-only base class, so `update()`,
   `delete()`, and `delete_by_id()` do not exist on it — only `append()`.
2. The initial migration installs a PostgreSQL trigger,
   `trg_audit_events_append_only`, that raises on any `UPDATE` or `DELETE`.
   This holds for `psql`, admin tools, and future migrations alike.

Because deletes are blocked, `audit_events.incident_id` uses
`ON DELETE RESTRICT`: an incident that has audit events cannot be deleted.
Query the trail by `trace_id`, which outlives every other row.

`uv run pytest tests/test_audit_append_only.py` proves both layers hold.

---

## Not in scope yet

No authentication, LLM/MCP calls, Litmus/MES/ERP/CMMS integrations, Teams
notifications, or live telemetry. What stands in for them:

- **Agents** — `app/services/simulation.py` writes the `agent_runs` rows a real
  sentinel/diagnosis/planner/parts pipeline would produce. `model_name` and
  `model_version` are recorded for provenance; no model is invoked.
- **CMMS** — approving creates a work order with the fixed external reference
  `WO-40219`. A real adapter would take that from the CMMS response.
- **Inventory** — part reservation flips `part_checks.status` to `reserved` and
  stamps `reserved_at`. Nothing leaves the process.
- **Telemetry** — the sentinel anomalies are seeded, not ingested.

Nothing in this repository talks to a network service other than its own
PostgreSQL database.

See `tasks.md` for what is done and what comes next.
