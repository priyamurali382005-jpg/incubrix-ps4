import collections
import hmac
import threading
import time

from fastapi import Request

from app import config
from app.errors import error_response

PROTECTED = ("/api/v1/", "/connector/v1/")
OPEN_PATHS = {"/api/v1/health", "/api/v1/ready"}
TOKEN_EXEMPT_PREFIX = "/api/v1/files/"
_hits: dict = collections.defaultdict(collections.deque)
_lock = threading.Lock()


def reset():
    with _lock:
        _hits.clear()


def _ip(request: Request) -> str:
    if config.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def guard(request: Request, call_next):
    path = request.url.path
    if path.startswith(PROTECTED) and path not in OPEN_PATHS:
        if config.API_TOKEN and not path.startswith(TOKEN_EXEMPT_PREFIX):
            supplied = (
                request.headers.get("x-api-key")
                or request.headers.get("authorization", "").removeprefix("Bearer ")
            )
            if not hmac.compare_digest(
                supplied.encode(), config.API_TOKEN.encode()
            ):
                return error_response(
                    "UNAUTHORIZED", "Missing or wrong access token."
                )

        if config.RATE_LIMIT_PER_MIN > 0:
            now = time.monotonic()
            with _lock:
                window = _hits[_ip(request)]
                while window and now - window[0] > 60:
                    window.popleft()

                if len(window) >= config.RATE_LIMIT_PER_MIN:
                    retry = int(60 - (now - window[0])) + 1
                    resp = error_response(
                        "RATE_LIMITED",
                        "Too many requests. Slow down.",
                        {"retry_after_s": retry},
                    )
                    resp.headers["Retry-After"] = str(retry)
                    return resp

                window.append(now)

    return await call_next(request)
