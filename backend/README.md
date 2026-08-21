# AMC Backend

FastAPI + SQLAlchemy 2.0 (async) + Alembic backend for the Autonomous
Maintenance Console. See the [root README](../README.md) for full setup
instructions; the quick version, run from this directory:

```bash
uv sync                                  # install dependencies
uv run alembic upgrade head              # apply migrations
uv run uvicorn app.main:app --reload     # serve on http://localhost:8000
uv run pytest                            # run the test suite
uv run ruff check .                      # lint
```

## Layout

| Path                | Responsibility                                        |
| ------------------- | ----------------------------------------------------- |
| `app/api/`          | HTTP routing and FastAPI dependencies                 |
| `app/core/`         | Settings, logging, middleware, error handling         |
| `app/db/`           | Declarative base, async engine, session dependency    |
| `app/models/`       | SQLAlchemy ORM models (the source for migrations)     |
| `app/schemas/`      | Pydantic request/response models                      |
| `app/repositories/` | All SQL — the only layer that queries the database    |
| `app/services/`     | Business logic orchestrating repositories             |
| `alembic/`          | Migration environment and revision scripts            |
| `tests/`            | pytest suite                                          |
