# Link Shortener

<p align="left">
  <img src="frontend/public/images/logo.png" alt="Link Shortener" width="160" />
</p>

Simple link shortener with a clean UI and fast redirects.

## Features

- **Fast redirects**
- **Custom short links** (your own suffix)
- **Optional expiry** (or never expires)
- **Basic rate limiting**
- **Nice share previews** (uses the destination preview when available, otherwise falls back to this site)
- **SEO-friendly landing page**

## Quick start (Docker)

```bash
docker build -t link-shortener:latest .
docker run --rm -p 127.0.0.1:17320:17320 -p 127.0.0.1:17321:17321 --env-file backend/.env link-shortener:latest
```

Open `http://localhost:17320`.

Health endpoints:
- Liveness (container): `http://localhost:17321/api/live`
- Readiness/diagnostics: `http://localhost:17321/api/health` (also available at `/health`)

## Recommended production run (single container)

Run one container (frontend + backend + Redis together):

```bash
docker compose up -d --build
```

Use these `.env` values:

- `REDIS_HOST=127.0.0.1`
- `REDIS_PORT=6379`
- `REDIS_DB=0`
- `REDIS_PASSWORD=` (leave empty)
- `MYSQL_HOST=host.docker.internal` (if MySQL stays on host)

If MySQL runs on the Docker host (not in this stack), keep:

- `MYSQL_HOST=host.docker.internal`

and on Linux add:

```bash
--add-host=host.docker.internal:host-gateway
```

## Config

Copy `backend/.env.example` → `backend/.env` and edit values as needed.

## License

MIT © KasunCSB

