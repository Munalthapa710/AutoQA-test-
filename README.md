# autoqa-agent

`autoqa-agent` is a local-first MVP for automated end-to-end web app exploration.
It opens a target application with Playwright, explores it with conservative heuristics,
records each step, collects artifacts, detects failures, and exports readable Playwright
tests from successful flows.

This README is written for contributors first: how the repo is organized, how to run it,
how to test it, and what to expect from the current implementation.

## What this project does

- Saves reusable run configurations for a target web app
- Queues and executes exploratory runs
- Logs every browser action, locator, rationale, URL, title, and outcome
- Captures artifacts such as screenshots, traces, JSON reports, and generated tests
- Detects common failures from multiple signals:
  - action and assertion failures
  - browser console errors
  - network request failures
  - lightweight accessibility findings
  - low-confidence exploration stop conditions
- Exposes a dashboard for viewing runs, steps, failures, artifacts, and generated tests

## Stack

- Frontend: Next.js 15, React 19, TypeScript, Tailwind CSS
- API: FastAPI, Pydantic, SQLAlchemy, Alembic
- Worker: Python, LangGraph, Playwright
- Infra: PostgreSQL, Redis, Docker Compose
- Local fallback storage: SQLite and filesystem-backed queue/artifacts

## Repository layout

```text
autoqa-agent/
├── apps/
│   ├── api/                 # FastAPI app and Alembic migrations
│   ├── web/                 # Next.js dashboard
│   └── worker/              # Run execution worker
├── packages/python/
│   └── autoqa_shared/       # Shared Python models, queue, db, explorer logic
├── artifacts/               # Persisted screenshots, traces, reports
├── generated-tests/         # Exported Playwright specs
├── tests/                   # Python tests
├── docker-compose.yml
└── README.md
```

## How it works

At a high level:

1. The API stores configs and run metadata.
2. A worker dequeues pending runs.
3. Playwright launches the target app and explores it.
4. Each step is logged and validated.
5. Artifacts and generated tests are written to disk.
6. The dashboard displays the results.

The worker currently follows a deterministic, safety-oriented exploration flow:

1. open the configured page
2. log in when credentials exist
3. inspect the visible page state
4. classify actions by risk
5. prioritize safe and useful flows
6. validate the page after each action
7. stop on max steps or repeated uncertainty
8. export successful flows into Playwright specs

## Quick start with Docker

Use Docker when you want the full stack with PostgreSQL and Redis.

### Prerequisites

- Docker Desktop or Docker Engine with Compose support

### Start the stack

```bash
cp .env.example .env
docker compose up --build
```

### URLs

- Dashboard: `http://localhost:3002`
- API docs: `http://localhost:8000/docs`
- API health: `http://localhost:8000/health`

### Stop the stack

```bash
docker compose down
```

## Local development

Local development is often the fastest contributor workflow.
This repo supports a useful fallback mode when PostgreSQL or Redis are not available:

- database falls back to local SQLite
- queue falls back to a local JSON-backed store

That means you can run the project without Docker for most development work.

### Recommended prerequisites

- Python 3.12 or 3.13
- Node.js 20+
- npm 10+

Notes:

- Python 3.14 may work for parts of the stack, but some transitive dependencies still warn about compatibility.
- Docker is optional for local development.

### 1. Clone and enter the repo

```bash
git clone <your-fork-or-repo-url>
cd autoqa-agent
```

### 2. Create the environment file

```bash
cp .env.example .env
```

You can leave `.env` minimal for local fallback mode.
If you want to point at real PostgreSQL or Redis instances, update:

- `DATABASE_URL`
- `REDIS_URL`
- `NEXT_PUBLIC_API_BASE_URL`

### 3. Create a virtual environment and install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-api.txt -r requirements-worker.txt
python -m playwright install chromium
```

### 4. Install frontend dependencies

From the repository root:

```bash
npm install --workspace apps/web
```

### 5. Export `PYTHONPATH`

```bash
export PYTHONPATH="$PWD/apps/api:$PWD/apps/worker:$PWD/packages/python"
```

### 6. Run the services

Open three terminals from the repo root.

API:

```bash
source .venv/bin/activate
DATABASE_URL=sqlite:///.runtime/autoqa-run.db \
PYTHONPATH="$PWD/apps/api:$PWD/apps/worker:$PWD/packages/python" \
uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

Worker:

```bash
source .venv/bin/activate
PYTHONPATH="$PWD/apps/api:$PWD/apps/worker:$PWD/packages/python" \
python -m worker.main
```

Web:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev:web
```

### Local URLs

- Dashboard: `http://localhost:3000`
- API docs: `http://127.0.0.1:8000/docs`
- API health: `http://127.0.0.1:8000/health`

## Running tests

From the repo root:

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD/apps/api:$PWD/apps/worker:$PWD/packages/python"
python -m pytest tests
```

Current test coverage focuses mainly on:

- API run controls
- SQLite fallback behavior
- explorer sampling and CRUD scope logic

## Common contributor tasks

### Reinstall frontend dependencies

```bash
npm install --workspace apps/web
```

### Reinstall Python dependencies

```bash
source .venv/bin/activate
pip install -r requirements-api.txt -r requirements-worker.txt
```

### Reset local runtime data

The repo writes local runtime files under `./.runtime/`.
If your local fallback database gets into a bad state, remove only the runtime files you intend to reset.

Examples:

- SQLite fallback db: `./.runtime/autoqa-dev.db` or `./.runtime/autoqa-run.db`
- local queue/report data: `./.runtime/artifacts/`

Be careful not to remove checked-in artifact folders unless that is intentional.

## Environment variables

Common variables used by the stack:

- `DATABASE_URL`
- `REDIS_URL`
- `API_PUBLIC_BASE_URL`
- `NEXT_PUBLIC_API_BASE_URL`
- `ARTIFACTS_ROOT`
- `GENERATED_TESTS_ROOT`
- `PLAYWRIGHT_HEADLESS`
- `SAFE_MODE_DEFAULT`
- `WORKER_QUEUE_NAME`
- `WORKER_POLL_TIMEOUT`

See `.env.example` for the default values used by Docker-oriented setups.

## Main API endpoints

- `POST /configs`
- `GET /configs`
- `GET /configs/{id}`
- `POST /runs`
- `GET /runs`
- `GET /runs/{id}`
- `GET /runs/{id}/steps`
- `GET /runs/{id}/flows`
- `GET /runs/{id}/failures`
- `GET /runs/{id}/artifacts`
- `GET /generated-tests`
- `GET /generated-tests/{id}`
- `GET /health`

## Artifacts and outputs

Generated data is stored in these locations:

- `./artifacts/screenshots`
- `./artifacts/traces`
- `./artifacts/reports`
- `./generated-tests`

In local fallback mode, some runtime-managed files may also be created under:

- `./.runtime/`

## Current limitations

- Complex SSO and advanced auth flows are out of scope for the current login heuristics
- Accessibility checks are lightweight and not a full `axe-core` style audit
- Safe mode reduces destructive actions but cannot perfectly infer every irreversible action
- Exploration uses deterministic heuristics rather than an LLM planner
- Video capture is not currently included

## Troubleshooting

### `docker: command not found`

Use the local development workflow instead of Docker.

### `next: command not found`

Make sure frontend dependencies were installed from the repo root:

```bash
npm install --workspace apps/web
```

### API cannot connect to PostgreSQL

That is expected if you are not running Postgres locally.
For local development, use the SQLite fallback command shown above:

```bash
DATABASE_URL=sqlite:///.runtime/autoqa-run.db uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

### Redis is not running

The worker can fall back to a local JSON-backed queue store for local development.

### Playwright browser launch fails

Install the browser runtime:

```bash
source .venv/bin/activate
python -m playwright install chromium
```

### Local fallback SQLite file behaves strangely

Delete the specific runtime database file you want to reset and start the API again.
Do not remove unrelated tracked project files.

## Contributing

A good baseline workflow for contributors:

1. create a branch
2. install dependencies
3. run the API, worker, and web app locally
4. make focused changes
5. run tests
6. verify the dashboard or API behavior manually when relevant

When changing behavior in shared exploration logic, please prefer:

- small, reviewable commits
- tests for bug fixes or control-flow changes
- notes in the PR about any artifact or runtime format changes

## Attribution

This enhancement branch is based on the original project by `chuchu387`.

Current work in this repository builds on that codebase with local-run improvements,
dashboard cleanup, and contributor-focused quality-of-life fixes.
