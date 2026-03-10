# autoqa-agent

`autoqa-agent` is a runnable MVP for agentic end-to-end web app exploration. It accepts a target URL and login details, launches Playwright, explores the app with conservative heuristics, records every step, detects failures from multiple oracles, stores artifacts locally, and exports readable Playwright specs from successful flows.

## Stack

- Frontend: Next.js, TypeScript, Tailwind CSS
- API: FastAPI, Pydantic, SQLAlchemy, Alembic
- Worker: Python, LangGraph, Playwright
- Infra: PostgreSQL, Redis, Docker Compose
- Storage: local filesystem under `./artifacts` and `./generated-tests`

## Monorepo layout

```text
autoqa-agent/
├── apps/
│   ├── api/
│   ├── web/
│   └── worker/
├── packages/python/autoqa_shared/
├── artifacts/
│   ├── screenshots/
│   ├── traces/
│   └── reports/
└── generated-tests/
```

## What the MVP does

- creates saved run configurations
- queues and executes runs with Redis-backed workers
- logs every browser action, rationale, locator, URL, page title, and result
- detects:
  - action and assertion failures
  - browser console errors
  - network request failures
  - screenshot evidence
  - accessibility findings from a DOM audit
  - low-confidence exploration stop conditions
- stores screenshots, JSON reports, traces, and generated specs on disk
- exposes a dashboard for run history, live step logs, discovered flows, failures, generated tests, and artifact previews

## Quick start with Docker

1. Copy the environment file.

```bash
cd /home/selroti/autoqa-agent
cp .env.example .env
```

2. Build and start the full stack.

```bash
docker compose up --build
```

3. Open the services.

- Dashboard: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

Artifacts land in:

- `./artifacts/screenshots`
- `./artifacts/traces`
- `./artifacts/reports`
- `./generated-tests`

## Local development

### Prerequisites

- Python 3.12+
- Node 20+
- PostgreSQL 16+
- Redis 7+
- Chromium installed for Playwright

### 1. Environment

```bash
cd /home/selroti/autoqa-agent
cp .env.example .env
export PYTHONPATH="$PWD/apps/api:$PWD/apps/worker:$PWD/packages/python"
```

If you run PostgreSQL or Redis locally instead of Docker, update `.env` so `DATABASE_URL` and `REDIS_URL` point to them.

### 2. Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-api.txt -r requirements-worker.txt
playwright install chromium
```

### 3. Frontend dependencies

```bash
cd /home/selroti/autoqa-agent/apps/web
npm install
cd /home/selroti/autoqa-agent
```

### 4. Database migration

```bash
cd /home/selroti/autoqa-agent/apps/api
alembic upgrade head
cd /home/selroti/autoqa-agent
```

### 5. Run each service

API:

```bash
cd /home/selroti/autoqa-agent
source .venv/bin/activate
export PYTHONPATH="$PWD/apps/api:$PWD/apps/worker:$PWD/packages/python"
uvicorn app.main:app --app-dir /home/selroti/autoqa-agent/apps/api --host 0.0.0.0 --port 8000
```

Worker:

```bash
cd /home/selroti/autoqa-agent
source .venv/bin/activate
export PYTHONPATH="$PWD/apps/api:$PWD/apps/worker:$PWD/packages/python"
python -m worker.main
```

Web:

```bash
cd /home/selroti/autoqa-agent/apps/web
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

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

## How exploration works

The worker uses a LangGraph state machine:

1. bootstrap browser and open the configured entry page
2. perform login when credentials exist
3. inspect current page structure and visible interactive elements
4. classify each possible action as safe, risky, or destructive
5. prioritize create, edit, search, filter, settings, and view flows
6. skip destructive actions in safe mode
7. execute the best remaining action with semantic Playwright locators when possible
8. validate console errors, network failures, page stability, and accessibility after each action
9. stop on max steps or repeated uncertainty
10. export successful flows into Playwright specs

## Generated test output

Successful flows are saved as readable TypeScript specs under `./generated-tests`. The dashboard shows the code inline and links to the underlying file.

## Known limitations

- login heuristics are good enough for common username/password forms, but complex SSO flows are out of scope for this MVP
- accessibility scanning is a lightweight DOM audit, not a full axe-core integration
- safe mode blocks obviously destructive actions, but cannot perfectly infer every irreversible admin operation
- the exploration planner uses deterministic heuristics instead of an LLM policy, which keeps the MVP reproducible but less adaptive
- screenshots are captured after each executed step; video capture is not included
