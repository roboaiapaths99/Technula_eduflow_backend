"""
Rate Limiter Middleware — Sliding window rate limiting for sensitive endpoints
(Login, OTP requests, Password Resets) to prevent brute-force attacks and abuse.
"""
import time
from collections import defaultdict
from typing import Dict, List
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitRule:
    def __init__(self, prefix: str, max_requests: int, window_seconds: int):
        self.prefix = prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds


# Define sensitive endpoint rate limits
RATE_LIMIT_RULES = [
    RateLimitRule(prefix="/auth/login", max_requests=10, window_seconds=60),
    RateLimitRule(prefix="/auth/superadmin/send-otp", max_requests=5, window_seconds=60),
    RateLimitRule(prefix="/auth/parent/send-otp", max_requests=5, window_seconds=60),
    RateLimitRule(prefix="/auth/forgot-password", max_requests=5, window_seconds=60),
    RateLimitRule(prefix="/auth/reset-password", max_requests=10, window_seconds=60),
]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # Store timestamp history per (client_ip, prefix)
        self._history: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Match against sensitive endpoint rules
        rule = None
        for r in RATE_LIMIT_RULES:
            if path.startswith(r.prefix):
                rule = r
                break

        if rule and request.method in ["POST", "PUT"]:
            client_ip = request.client.host if request.client else "unknown"
            key = f"{client_ip}:{rule.prefix}"
            now = time.time()
            cutoff = now - rule.window_seconds

            # Clean expired timestamps
            timestamps = [t for t in self._history[key] if t > cutoff]
            if len(timestamps) >= rule.max_requests:
                retry_after = int(rule.window_seconds - (now - timestamps[0])) + 1
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Too many requests. Please wait {retry_after} seconds before trying again.",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)
            self._history[key] = timestamps

        response = await call_next(request)
        return response
