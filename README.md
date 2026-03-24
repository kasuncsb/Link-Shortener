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
docker run --rm -p 17320:17320 -p 17321:17321 --env-file backend/.env link-shortener:latest
```

Open `http://localhost:17320`.

If MySQL/Redis run on the Docker host (not in this container), set:

- `MYSQL_HOST=host.docker.internal`
- `REDIS_HOST=host.docker.internal`

and on Linux add:

```bash
--add-host=host.docker.internal:host-gateway
```

## Config

Copy `backend/.env.example` → `backend/.env` and edit values as needed.

## License

MIT © KasunCSB

