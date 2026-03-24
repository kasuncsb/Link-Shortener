# Link Shortener

<p align="left">
  <img src="frontend/public/images/logo.png" alt="Link Shortener" width="240" />
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
docker run --rm -p 3000:3000 -p 17321:17321 --env-file backend/.env link-shortener:latest
```

Open `http://localhost:3000`.

## Config

Copy `backend/.env.example` → `backend/.env` and edit values as needed.

## License

MIT © KasunCSB

