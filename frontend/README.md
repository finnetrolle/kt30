# Frontend

This directory contains the standalone frontend migration target for KT30.

Current scope:

- React + Vite + TypeScript scaffold
- TanStack Router routes for `login`, `upload/progress`, and `results`
- React Query data layer
- API client wired to the new Flask headless endpoints
- Vite dev proxy for `/api`, `/health`, and `/ready`

## Start

Install dependencies and run the dev server:

```bash
npm install
npm run dev
```

By default Vite runs on `http://localhost:5173` and proxies API traffic to `http://localhost:8000`.

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
- The legacy Flask templates remain available until feature parity is complete.
