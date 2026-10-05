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


from fastapi.responses import HTMLResponse


@app.get("/privacy", response_class=HTMLResponse)
@app.get("/privacy-policy", response_class=HTMLResponse)
@app.get("/data-deletion", response_class=HTMLResponse)
def public_privacy_policy():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Technula EduFlow — Privacy Policy & Data Safety</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.7; color: #1e293b; max-width: 820px; margin: 0 auto; padding: 40px 20px; }
    h1 { color: #0f172a; font-size: 28px; }
    h2 { color: #1e293b; font-size: 18px; margin-top: 24px; }
    .badge { display: inline-block; background: #eff6ff; color: #2563eb; font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 999px; margin-bottom: 8px; }
    .card { background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; padding: 16px; margin: 20px 0; color: #7c2d12; }
    a { color: #2563eb; font-weight: 600; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="badge">OFFICIAL PRIVACY & DATA SAFETY POLICY</div>
  <h1>Technula EduFlow Privacy Policy</h1>
  <p><small>Last Updated: October 2026 • Valid for Mobile Apps and Web Portals</small></p>

  <h2>1. Overview & Purpose</h2>
  <p>Technula EduFlow is an educational management portal designed for authorized schools, teachers, students, and their parents/guardians to access student attendance, academic report cards, fee receipts, digital gate passes, and school circulars.</p>

  <h2>2. Data We Collect</h2>
  <ul>
    <li><strong>Parent/Guardian Profile:</strong> Name, registered mobile number, email address.</li>
    <li><strong>Student Records:</strong> Name, class, section, attendance marks, exam grades, homework, and fee receipts.</li>
    <li><strong>Device & Push Tokens:</strong> Firebase Cloud Messaging (FCM) tokens strictly for urgent school notices and attendance updates.</li>
  </ul>

  <h2>3. What We DO NOT Collect</h2>
  <ul>
    <li>We do NOT track continuous GPS location.</li>
    <li>We do NOT record audio, access device microphones, or read private SMS.</li>
    <li>We do NOT store payment card details (all tuition payments are processed via RBI/PCI-DSS certified gateways).</li>
    <li>We NEVER sell, trade, or share user data with third-party advertisers.</li>
  </ul>

  <h2>4. Student & Child Data Protection (COPPA / FERPA)</h2>
  <p>Student profiles are private and accessible exclusively to their authenticated legal guardians and assigned teachers. No student information is publicly visible or indexed by search engines.</p>

  <div class="card">
    <h3 style="margin-top:0; color:#9a3412;">5. User Data & Account Deletion (Google Play Compliance)</h3>
    <p>Users have the right to request deletion of their account and personal data at any time.</p>
    <p><strong>How to request deletion:</strong> Inside the mobile app, tap <em>Menu &rarr; Guardian Profile &rarr; Delete Account &amp; Data</em>, or email <a href="mailto:sales@technula.com">sales@technula.com</a> with your registered mobile number.</p>
  </div>

  <h2>6. Contact Us</h2>
  <p>Technula EduFlow Privacy Office: <a href="mailto:sales@technula.com">sales@technula.com</a> | Portal: <a href="https://technulaeduflow.technula.com">https://technulaeduflow.technula.com</a></p>
</body>
</html>"""



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
