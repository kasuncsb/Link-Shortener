<p align="center">
  <img src="frontend/public/favicon.ico" alt="Link Shortener" width="72" />
</p>

# Link Shortener

A fast, production-ready URL shortener built with **FastAPI + MySQL + Redis** and a lightweight **static frontend** served by Express. Designed for clean redirects, optional expirations, and easy self-hosting.

## Features
- Shorten URLs with optional custom codes
- Expiring links with UTC-safe timestamps
- Redis-backed caching + rate limiting
- Stats + preview endpoints
- HTML error pages (404 / 410) for browsers
- Single-container or split deployment options

## Architecture
- **Backend:** FastAPI, SQLAlchemy, MySQL, Redis
- **Frontend:** Static assets served by Express (`frontend/server.js`)
- **Cache/Rate Limit:** Redis

## Requirements
- Python 3.11+
- Node.js 20+
- MySQL 8+
- Redis 6+

## Configuration

### Backend (.env)
File: `backend/.env`

Key variables:
```
APP_NAME=Link Shortener
APP_VERSION=1.0.0
DEBUG=false
BASE_URL=https://lk.kasunc.uk

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=linkshortener
MYSQL_PASSWORD=your_secure_password
MYSQL_DATABASE=link_shortener

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=1
REDIS_PASSWORD=

DEFAULT_EXPIRY_DAYS=30
MIN_CUSTOM_CODE_LENGTH=5
MAX_CUSTOM_CODE_LENGTH=20

RESERVED_CODES=["api","admin","www","static","assets","health","robots.txt","favicon.ico","sitemap.xml"]
```

### Frontend API Base
File: `frontend/public/config.json`

Set this to wherever your backend is reachable:
```
{ "API_BASE": "http://localhost:17321" }
```

For production:
```
{ "API_BASE": "https://lk.kasunc.uk" }
```

## Database Setup

1) Create DB + table:
```
mysql -u root -p < backend/schema.sql
```

2) The backend sets DB session time to UTC on connect, and `expires_at` is stored as UTC.

## Run Locally (without Docker)

Backend:
```
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:
```
cd frontend
npm install
npm run dev
```

Update `frontend/public/config.json` to match the backend port if needed.

## Run with Docker (single container, two ports)

This container runs:
- Frontend on **17320**
- Backend on **17321**

Build:
```
docker build -t link-shortener .
```

Run (host networking, best if MySQL/Redis are bound to localhost):
```
docker run -d --name link-shortener --restart unless-stopped \
  --network host \
  --env-file backend/.env \
  link-shortener
```

Run (bridge networking):
```
docker run -d --name link-shortener --restart unless-stopped \
  -p 17320:17320 -p 17321:17321 \
  --env-file backend/.env \
  -e MYSQL_HOST=172.17.0.1 \
  -e REDIS_HOST=172.17.0.1 \
  link-shortener
```

## Production Nginx (single domain)

If you want `https://lk.kasunc.uk/<code>` to redirect correctly:
- Frontend on port **17320**
- Backend on port **17321**

Use an nginx config that routes:
- `/api/*` → backend
- `/anything` (short codes) → backend
- `/` → frontend

Example (short-code matcher is permissive):
```
location /api/ { proxy_pass http://127.0.0.1:17321; }
location ~ ^/[^./]+$ { proxy_pass http://127.0.0.1:17321; }
location / { proxy_pass http://127.0.0.1:17320; }
```

## API Endpoints
- `POST /api/shorten`
- `GET /api/stats/{code}`
- `GET /api/preview/{code}`
- `GET /api/check/{code}`
- `GET /{code}` (redirect)
- `GET /health`

**Status codes**
- `404` not found
- `410` expired

## Troubleshooting
- **“Link unavailable” page**: request is hitting the frontend; route short codes to backend.
- **MySQL connection refused**: use `--network host` or set `MYSQL_HOST=172.17.0.1`.
- **Redis connection refused**: set `REDIS_HOST=172.17.0.1` or run with host networking.

