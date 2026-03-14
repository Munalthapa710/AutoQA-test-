# Production Deploy

This repo is easiest to deploy on one Linux VPS with Docker Compose.

## 1. Prepare the server

- Install Docker Engine and the Docker Compose plugin.
- Clone the repository.
- Copy `.env.production.example` to `.env.production`.
- Replace the placeholder values in `.env.production`.

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

Use `deploy/nginx.autoqa.conf.example` as the starting point for Nginx.

Suggested domains:

- `app.example.com` -> web on `127.0.0.1:3000`
- `api.example.com` -> api on `127.0.0.1:8000`

After Nginx is in place, add TLS with Let's Encrypt.

## 5. Updates

To deploy a new version:

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production up --build -d
```

## Notes

- PostgreSQL and Redis are intentionally not exposed publicly in `docker-compose.prod.yml`.
- Artifacts and generated tests stay on the server filesystem, so back up `artifacts/` and `generated-tests/`.
- The worker runs Playwright and may need more memory on small VPS instances.
