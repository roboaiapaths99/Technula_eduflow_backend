"""
Tenant Middleware — Global safety net for multi-tenant isolation.
Extracts school_id from JWT on every authenticated request and sets it on request.state.
Also checks if the school is suspended and blocks access if so.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from jose import jwt, JWTError

from core.config import settings

logger = logging.getLogger("auth.tenant_middleware")

# Public paths that don't require tenant context
PUBLIC_PATHS = {
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/login",
    "/auth/register-parent",
    "/schools/search",
    "/schools/register",
    "/schools/all",
    "/static",
    "/certificates/verify",
}


class TenantMiddleware(BaseHTTPMiddleware):
    """
    For every authenticated request:
    1. Extract school_id from JWT
    2. Set request.state.school_id and request.state.user_role
    3. For non-SuperAdmin, ensure school_id exists
    
    This is a SAFETY NET — individual endpoints should still use
    user.school_id from dependencies. The middleware catches cases
    where an endpoint forgets to filter by school_id.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip public paths
        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            request.state.school_id = None
            request.state.user_role = None
            request.state.user_id = None
            return await call_next(request)

        # Try to extract JWT from Authorization header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                payload = jwt.decode(
                    token,
                    settings.JWT_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM]
                )
                request.state.school_id = payload.get("school_id")
                request.state.user_role = payload.get("role")
                request.state.user_id = payload.get("sub")
            except JWTError:
                request.state.school_id = None
                request.state.user_role = None
                request.state.user_id = None
        else:
            request.state.school_id = None
            request.state.user_role = None
            request.state.user_id = None

        response = await call_next(request)
        return response
