# Frontend (placeholder)

The React frontend for the Autonomous Maintenance Console has **not** been built
yet — this directory is intentionally empty apart from this file.

Planned stack (subject to change when the UI task starts):

- React + TypeScript, built with Vite
- Dev server on `http://localhost:5173` (already allow-listed by the backend
  CORS configuration, see `CORS_ORIGINS` in `.env.example`)
- Talks to the FastAPI backend under the `API_PREFIX` (`/api/v1` by default)

Until then, see the [root README](../README.md) for how to run the backend.
