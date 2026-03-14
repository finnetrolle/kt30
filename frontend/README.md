# Frontend

This directory contains the standalone frontend migration target for KT30.

Current scope:

- React + Vite + TypeScript scaffold
- TanStack Router routes for `login`, `upload/progress`, and `results`
- React Query data layer
- API client wired to the new Flask headless endpoints
- Vite dev proxy for `/api`, `/health`, and `/ready`
- richer results view with token stats, assumptions, risks, recommendations, JSON export

## Start

Install dependencies and run the dev server:

```bash
npm install
npm run dev
npm test
npm run test:e2e
```

By default Vite uses the same base path as Flask (`FRONTEND_ROUTE_PREFIX=app`), so the frontend opens on `http://localhost:5173/app/` and proxies API traffic to `http://localhost:8000`.

If you want a different base path for the standalone app, set one of:

```bash
FRONTEND_ROUTE_PREFIX=app
VITE_APP_BASE_PATH=/app/
```

## Production-style serving through Flask

After the frontend is built, Flask can serve it under `/app`:

```bash
npm run build
```

Then enable:

```bash
SERVE_FRONTEND_BUILD=true
FRONTEND_DIST_DIR=frontend/dist
FRONTEND_ROUTE_PREFIX=app
```

With that configuration the built SPA is served from:

- `/app`
- `/app/login`
- `/app/results/:resultId`

## Backend requirements

Run the Flask web app and worker as usual:

```bash
python app.py
python worker.py
```

The frontend expects the following backend routes to exist:

- `GET /api/auth/session`
- `GET /api/auth/csrf`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `POST /api/uploads`
- `GET /api/tasks/:taskId/events`
- `POST /api/tasks/:taskId/cancel`
- `GET /api/results/:resultId`
- `GET /api/results/:resultId/export.xlsx`

## Notes

- This is an in-repo migration scaffold, not the final production packaging yet.
- Flask now treats the standalone frontend as the primary UI and keeps `/`, `/login`, and `/results/:id` only as compatibility redirects into `/app`.
- The upload/progress page now stores `taskId` in the URL search params so an in-flight analysis can be reopened after a refresh.
- `Vitest` is configured for component and API-client coverage of the standalone frontend flows.
- `Playwright` now covers the browser-level `login -> upload -> progress -> results` flow against a preview server with mocked API routes.
- The e2e suite also covers auth failure, cancel flow, missing task recovery, and missing result recovery.
- The e2e suite currently uses the locally installed Google Chrome channel.
