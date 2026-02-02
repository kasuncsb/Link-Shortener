from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from pathlib import Path
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from .env import get_env, get_bool, get_list, get_bool_optional
from .database import engine, Base, get_db
from .routes import router as api_router, get_client_ip
from .services import LinkService
from .redis_client import RedisService, redis_client
from .models import Link
from .utils import utc_now, normalize_utc
from .logging_config import setup_logging, get_logger, set_request_id, get_request_id
from .tasks import task_runner

# Initialize structured logging
setup_logging()
logger = get_logger(__name__)

PUBLIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to each request for tracing."""
    
    async def dispatch(self, request: Request, call_next):
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID")
        rid = set_request_id(request_id)
        
        # Process request
        response = await call_next(request)
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = rid
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Link Shortener API...")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
    
    # Rebuild Redis cache from the database (flush then load all entries)
    try:
        db = next(get_db())

        # Flush Redis completely so we load a fresh state
        try:
            redis_client.flushdb()
            logger.info("Flushed Redis database")
        except Exception as e:
            logger.error(f"Failed to flush Redis: {e}")

        now = utc_now()

        # Count expired links (do NOT delete — keep suffixes reserved)
        try:
            expired_count = db.query(Link).filter(Link.expires_at != None).filter(Link.expires_at < now).count()
        except Exception:
            expired_count = 0

        loaded = 0
        skipped = 0
        links = db.query(Link).all()
        for link in links:
            try:
                code = getattr(link, "suffix", None)
                url = getattr(link, "destination", None)
                expires_at_val = normalize_utc(getattr(link, "expires_at", None))

                # Skip expired links (keep DB rows so suffixes remain reserved)
                if expires_at_val and expires_at_val < now:
                    skipped += 1
                    continue

                # Cache non-expired entries in Redis with TTL matching DB expiry (or persist if none)
                if url and code:
                    RedisService.cache_link(code, url, expires_at=expires_at_val)
                    RedisService.add_code_to_set(code)
                    loaded += 1
            except Exception:
                # Skip problematic rows
                continue

        db.commit()
        logger.info(f"Loaded {loaded} link entries into Redis")
        if expired_count:
            logger.info(f"Found {expired_count} expired link rows in DB; skipped caching to keep suffixes reserved")
        if skipped:
            logger.info(f"Skipped caching {skipped} expired links during startup")
        db.close()
    except Exception as e:
        logger.error(f"Failed to rebuild Redis cache from DB: {e}")
    
    # Start background cleanup tasks
    task_runner.start()
    
    yield
    
    # Shutdown
    task_runner.stop()
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

# Request ID middleware for tracing
app.add_middleware(RequestIdMiddleware)

# CORS middleware - configured via environment
cors_origins = get_list("CORS_ORIGINS", ["*"])
if cors_origins == ["*"]:
    logger.warning("CORS configured to allow all origins. Set CORS_ORIGINS for production.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api", tags=["API"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    db_healthy = True
    redis_healthy = RedisService.health_check()
    
    try:
        from sqlalchemy import text
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_healthy = False
    
    status = "healthy" if (db_healthy and redis_healthy) else "degraded"
    
    return {
        "status": status,
        "database": db_healthy,
        "redis": redis_healthy,
        "version": get_env("APP_VERSION")
    }


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

    url, expired = LinkService.get_original_url(db, code_lower)

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
    
    # 301 for permanent redirect (better for SEO), 302 for temporary
    return RedirectResponse(url=url, status_code=301)


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
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return JSONResponse(status_code=exc.status_code or 500, content={"detail": exc.detail or "HTTP error"})


@app.exception_handler(Exception)
async def server_error_handler(request: Request, exc: Exception):
    logger.error(f"Server error: {exc}")
    return JSONResponse(status_code=500, content={"error": "Internal server error"})
