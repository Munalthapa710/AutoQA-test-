# Production Deploy

This repo is easiest to deploy on one Linux VPS with Docker Compose.

## 1. Prepare the server

- Install Docker Engine and the Docker Compose plugin.
- Clone the repository.
- Copy `.env.production.example` to `.env.production`.
- Replace the placeholder values in `.env.production`.
- Generate a Fernet key for `CREDENTIAL_ENCRYPTION_KEY` and keep a secure copy outside the database. The API and worker must use the same key. New passwords in production require the key. Existing plaintext configurations still work and must be recreated to encrypt them.

## 2. Start the stack

From the repository root:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up --build -d
```

## 3. Verify services

Check containers:

```bash
docker compose -f docker-compose.prod.yml ps
```

Check API health:

```bash
curl http://127.0.0.1:8000/health
```

Check web:

```bash
curl -I http://127.0.0.1:3000
```

## 4. Reverse proxy

Use `deploy/nginx.autoqa.conf.example` as the starting point. It serves the dashboard and its `/api/` routes, including artifact downloads, behind the same HTTP Basic login. Create `/etc/nginx/autoqa.htpasswd` with your password-file tool, grant Nginx read access, and serve the site over TLS before handing out credentials. Keep the API and dashboard ports bound to loopback. Use `NEXT_PUBLIC_API_BASE_URL=/api` when building the dashboard.

## 5. Updates

To deploy a new version:

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up --build -d
```

## Notes

- PostgreSQL and Redis are intentionally not exposed publicly in `docker-compose.prod.yml`.
- Artifacts and generated tests stay on the server filesystem, so back up `artifacts/` and `generated-tests/`.
- Older login flows and generated specs may contain credentials. Review old run data and backups, remove affected outputs, and rotate the corresponding target passwords. New login specs read `AUTOQA_TEST_USERNAME` and `AUTOQA_TEST_PASSWORD` from the test runner's environment. Runs with configured login details skip trace recording.
- The worker runs Playwright and may need more memory on small VPS instances.
