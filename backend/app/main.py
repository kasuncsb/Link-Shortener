from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
import logging
import os
from pathlib import Path
from html import escape
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

from .env import get_env, get_bool
from .database import engine, Base, get_db, SessionLocal
from .routes import router as api_router, get_client_ip
from .services import LinkService
from .redis_client import RedisService, redis_client
from .models import Link
from .utils import utc_now, normalize_utc
from .meta_fetcher import fetch_meta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PUBLIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public"
PREVIEW_BOT_HINTS = [
    "bot", "crawler", "spider", "slackbot", "twitterbot",
    "facebookexternalhit", "facebookcatalog", "linkedin", "discordbot",
    "whatsapp", "telegrambot", "skypeuripreview", "applebot",
    "googlebot", "bingbot", "yandexbot", "duckduckbot", "pinterest"
]


def _is_preview_bot(request: Request) -> bool:
    user_agent = (request.headers.get("user-agent") or "").lower()
    purpose = (request.headers.get("purpose") or "").lower()
    x_purpose = (request.headers.get("x-purpose") or "").lower()
    sec_purpose = (request.headers.get("sec-purpose") or "").lower()
    if "preview" in purpose or "preview" in x_purpose or "preview" in sec_purpose:
        return True
    return any(hint in user_agent for hint in PREVIEW_BOT_HINTS)


def _preview_html(short_url: str, destination_url: str, meta: dict) -> str:
    title = escape(str(meta.get("title") or "Link preview"))
    description = escape(str(meta.get("description") or "Open this link"))
    # Use destination image if available, otherwise fall back to service banner.
    image = str(meta.get("image") or f"{get_env('BASE_URL').rstrip('/')}/images/og-banner.jpg")
    domain = escape(str(meta.get("domain") or ""))
    image_tag = f'<meta property="og:image" content="{escape(image)}">' if image else ""
    image_secure_tag = f'<meta property="og:image:secure_url" content="{escape(image)}">' if image and image.startswith("https://") else ""
    twitter_image_tag = f'<meta name="twitter:image" content="{escape(image)}">' if image else ""

    return (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title>"
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{description}">'
        f'<meta property="og:url" content="{escape(short_url)}">'
        '<meta property="og:type" content="website">'
        f'{image_tag}'
        f'{image_secure_tag}'
        f'<meta name="twitter:title" content="{title}">'
        f'<meta name="twitter:description" content="{description}">'
        f'<meta name="twitter:card" content="summary_large_image">'
        f'{twitter_image_tag}'
        f'<link rel="canonical" href="{escape(destination_url)}">'
        "</head><body style=\"margin:0;background:#f6f9ff;font-family:Inter,Arial,sans-serif;\">"
        "<div style=\"max-width:680px;margin:48px auto;padding:0 20px;\">"
        "<div style=\"background:#fff;border:1px solid #dbe7ff;border-radius:16px;overflow:hidden;box-shadow:0 12px 40px rgba(29,78,216,.14);\">"
        f"<div style=\"padding:20px 20px 10px;color:#334155;font-size:12px;\">{domain or 'link preview'}</div>"
        f"<div style=\"padding:0 20px 8px;color:#0f172a;font-size:28px;line-height:1.2;font-weight:700;\">{title}</div>"
        f"<div style=\"padding:0 20px 18px;color:#334155;font-size:15px;line-height:1.5;\">{description}</div>"
        "</div>"
        "<div style=\"margin-top:14px;color:#64748b;font-size:12px;\">"
        f"Short link: {escape(short_url)}"
        "</div>"
        "</div>"
        "</body></html>"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Link Shortener API...")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
    
    # Rebuild Redis cache from the database (flush then load all entries)
    db = None
    try:
        db = SessionLocal()

        now = utc_now()

        # Count expired links (do NOT delete — keep suffixes reserved)
        try:
            expired_count = db.query(Link).filter(Link.expires_at != None).filter(Link.expires_at < now).count()
        except Exception:
            expired_count = 0

        loaded = 0
        skipped = 0
        to_cache = []
        expired_codes = []
        links = db.query(Link).all()
        for link in links:
            try:
                code = getattr(link, "suffix", None)
                url = getattr(link, "destination", None)
                expires_at_val = normalize_utc(getattr(link, "expires_at", None))

                # Expired links: don't cache the URL, but still reserve the suffix
                if expires_at_val and expires_at_val < now:
                    skipped += 1
                    if code:
                        expired_codes.append(code)
                    continue

                # Cache non-expired entries in Redis with TTL matching DB expiry (or persist if none)
                if url and code:
                    to_cache.append((code, url, expires_at_val))
                    loaded += 1
            except Exception:
                # Skip problematic rows
                continue

        # Clear old cache only after DB load succeeded, then repopulate.
        try:
            RedisService.clear_link_cache()
            logger.info("Cleared link cache keys in Redis")
            for code, url, expires_at_val in to_cache:
                RedisService.cache_link(code, url, expires_at=expires_at_val)
                RedisService.add_code_to_set(code)
            # Add expired codes to the used-codes set to prevent reuse
            for code in expired_codes:
                RedisService.add_code_to_set(code)
        except Exception as e:
            logger.error(f"Failed to rebuild Redis cache keys: {e}")

        db.commit()
        logger.info(f"Loaded {loaded} link entries into Redis")
        if expired_count:
            logger.info(f"Found {expired_count} expired link rows in DB; suffixes remain reserved")
        if skipped:
            logger.info(f"Skipped caching {skipped} expired links during startup")
    except Exception as e:
        logger.error(f"Failed to rebuild Redis cache from DB: {e}")
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
    
    yield
    
    # Shutdown
    logger.info("Shutting down Link Shortener API...")


app = FastAPI(
    title=get_env("APP_NAME"),
    version=get_env("APP_VERSION"),
    description="A fast, modern link shortening service",
    lifespan=lifespan,
    docs_url="/api/docs" if get_bool("DEBUG") else None,
    redoc_url="/api/redoc" if get_bool("DEBUG") else None
)

# Serve frontend assets for expired/404 pages when running backend standalone
if PUBLIC_DIR.exists():
    app.mount("/css", StaticFiles(directory=PUBLIC_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=PUBLIC_DIR / "js"), name="js")
    app.mount("/images", StaticFiles(directory=PUBLIC_DIR / "images"), name="images")
    app.mount("/animations", StaticFiles(directory=PUBLIC_DIR / "animations"), name="animations")

# Static HTML pages
@app.get("/expired.html", include_in_schema=False)
async def expired_page():
    page = PUBLIC_DIR / "expired.html"
    if page.exists():
        return FileResponse(page, status_code=410)
    return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/404.html", include_in_schema=False)
async def not_found_page():
    page = PUBLIC_DIR / "404.html"
    if page.exists():
        return FileResponse(page, status_code=404)
    return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    icon = PUBLIC_DIR / "favicon.ico"
    if icon.exists():
        return FileResponse(icon)
    return JSONResponse(status_code=404, content={"error": "Not found"})

# CORS middleware
_cors_raw = get_env("CORS_ORIGINS") if "CORS_ORIGINS" in os.environ else "*"
_cors_origins: list[str] = (
    ["*"] if _cors_raw.strip() == "*"
    else [o.strip() for o in _cors_raw.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api", tags=["API"])


def _health_payload() -> dict:
    """Build health payload used by both health endpoints."""
    db_healthy = True
    redis_healthy = RedisService.health_check()

    db = None
    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
    except Exception:
        db_healthy = False
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    status = "healthy" if (db_healthy and redis_healthy) else "degraded"

    return {
        "status": status,
        "database": db_healthy,
        "redis": redis_healthy,
        "version": get_env("APP_VERSION")
    }


@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Health check endpoint (supports /health and /api/health)."""
    return _health_payload()


@app.get("/{code}")
async def redirect_to_url(
    code: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Redirect short code to original URL."""
    # Skip static files and API routes
    if code in ["favicon.ico", "robots.txt", "sitemap.xml"]:
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    
    code_lower = code.lower()
    
    # Resolve URL (cache first, then DB). get_original_url returns (url, expired)
    accept = request.headers.get("accept", "")

    try:
        url, expired = LinkService.get_original_url(db, code_lower)
    except Exception:
        logger.exception("Failed to resolve short code '%s'", code_lower)
        if "text/html" in accept:
            return JSONResponse(status_code=503, content={"error": "Service temporarily unavailable"})
        return JSONResponse(status_code=503, content={"error": "Service temporarily unavailable"})

    if not url:
        if expired:
            if "text/html" in accept:
                page = PUBLIC_DIR / "expired.html"
                if page.exists():
                    return FileResponse(page, status_code=410)
                return JSONResponse(status_code=410, content={"error": "Link expired"})
            return JSONResponse(status_code=410, content={"error": "Link expired"})
        # not found
        if "text/html" in accept:
            page = PUBLIC_DIR / "404.html"
            if page.exists():
                return FileResponse(page, status_code=404)
            return JSONResponse(status_code=404, content={"error": "Link not found"})
        return JSONResponse(status_code=404, content={"error": "Link not found"})
    
    # Click recording removed per user's request
    
    force_preview = request.query_params.get("preview") == "1"
    if force_preview or _is_preview_bot(request):
        short_url = f"{get_env('BASE_URL').rstrip('/')}/{code_lower}"
        fallback_meta = {
            "title": get_env("APP_NAME"),
            "description": "TL;DR for your links. Get to the point. Fast & Secure.",
            "image": f"{get_env('BASE_URL').rstrip('/')}/images/og-banner.jpg",
            "domain": get_env("BASE_URL").replace("https://", "").replace("http://", ""),
        }
        try:
            meta = await fetch_meta(url)
        except Exception:
            meta = fallback_meta
        has_destination_preview = bool(
            meta and (
                (meta.get("image") and str(meta.get("image")).strip())
                or (meta.get("description") and str(meta.get("description")).strip())
            )
        )
        if not has_destination_preview:
            meta = fallback_meta
        return HTMLResponse(
            content=_preview_html(short_url=short_url, destination_url=url, meta=meta),
            status_code=200
        )

    # 301 for permanent links (better for SEO); 302 for expiring links
    # so browsers don't cache the redirect past the expiry date.
    link_obj = db.query(Link).filter(Link.suffix == code_lower).first()
    status = 302 if (link_obj is not None and link_obj.expires_at is not None) else 301
    return RedirectResponse(url=url, status_code=status)


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Handle 404 specially, otherwise return JSON using the exception's status code
    if getattr(exc, "status_code", None) == 404:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            page = PUBLIC_DIR / "404.html"
            if page.exists():
                return FileResponse(page, status_code=404)
        return JSONResponse(status_code=404, content={"error": "We couldn't find what you're looking for."})

    # Keep user-facing errors plain and non-technical.
    if exc.status_code == 400:
        message = "We couldn't process that request. Please check your input and try again."
    elif exc.status_code == 401:
        message = "Please sign in to continue."
    elif exc.status_code == 403:
        message = "You don't have access to this action."
    elif exc.status_code == 410:
        message = "This link is no longer available."
    elif exc.status_code == 429:
        message = "You're doing that too often. Please wait and try again."
    else:
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail.strip() else ""
        message = detail or "Something went wrong. Please try again."
    return JSONResponse(status_code=exc.status_code or 500, content={"error": message})


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    # Surface the first human-readable validation message without technical internals.
    message = "Please check your input and try again."
    try:
        first = exc.errors()[0] if exc.errors() else None
        if first:
            msg = first.get("msg")
            if isinstance(msg, str) and msg.strip():
                message = msg
    except Exception:
        pass
    return JSONResponse(status_code=422, content={"error": message})


@app.exception_handler(Exception)
async def server_error_handler(request: Request, exc: Exception):
    logger.error(f"Server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Something went wrong on our side. Please try again in a moment."}
    )
