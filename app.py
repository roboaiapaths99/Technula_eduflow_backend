from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from api import api_router
from db.init_db import init_db
from auth.tenant_middleware import TenantMiddleware
from core.rate_limiter import RateLimitMiddleware
from services.birthday_scheduler import start_birthday_scheduler_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch automated birthday wishes engine in background task
    birthday_task = asyncio.create_task(start_birthday_scheduler_loop())
    yield
    birthday_task.cancel()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# CORS middleware — support desktop, local network IPs, and mobile devices
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Correlation ID tracing middleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
import uuid
import logging

logger = logging.getLogger("app")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


app.add_middleware(CorrelationIdMiddleware)

# Rate limiting middleware for sensitive endpoints
app.add_middleware(RateLimitMiddleware)

# Tenant isolation middleware — extracts school_id from JWT on every request
app.add_middleware(TenantMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.error(f"[{correlation_id}] Unhandled error at {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Please try again later.",
            "error_type": type(exc).__name__,
            "correlation_id": correlation_id,
            "path": request.url.path,
        }
    )

# create tables
init_db()

app.include_router(api_router)

# Serve uploaded files & school assets (images, stamps, signatures, voice notes, PDFs, etc.)
static_dir = Path(__file__).parent / "static"
uploads_dir = static_dir / "uploads"
assets_dir = static_dir / "school_assets"
uploads_dir.mkdir(parents=True, exist_ok=True)
assets_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
def health_check():
    """Enhanced health check with real database connectivity validation."""
    db_status = "ok"
    try:
        from db.session import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as e:
        db_status = f"unhealthy: {e}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "version": "2.0.0",
        "environment": "development" if settings.DATABASE_URL.startswith("sqlite") else "production"
    }


@app.get("/health/integrations")
def health_integrations():
    from services.storage_service import test_storage_connection
    from services.gemini_service import test_gemini_connection
    return {
        "status": "ok",
        "storage": test_storage_connection(),
        "ai": test_gemini_connection(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["api", "auth", "core", "db", "models", "services"],
        reload_includes=["app.py"],
        reload_excludes=["venv", "venv/*", "*.db*", "__pycache__*"],
    )
