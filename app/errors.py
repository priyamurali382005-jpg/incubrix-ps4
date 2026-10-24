
from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        code,
        message,
        status=400,
        retryable=False,
        details=None,
    ):
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
        self.details = details or {}


async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
                "details": exc.details,
            }
        },
    )

# code -> (HTTP status, retryable)
CODE_INFO = {
    "DEST_SPEC_VIOLATION": (422, False),
    "DEST_RULE_FREQUENCY_CAP": (429, False),
    "CONNECTION_AUTH_EXPIRED": (401, False),
    "PLATFORM_RATE_LIMIT": (429, True),
    "PLATFORM_QUOTA_EXHAUSTED": (429, False),
    "PLATFORM_CONTENT_REJECTED": (422, False),
    "PLATFORM_UNAVAILABLE": (503, True),
    "CONNECTOR_DISABLED": (403, False),
    "CONNECTOR_NOT_FOUND": (404, False),
    "METHOD_NOT_SUPPORTED": (404, False),
    "IDEMPOTENCY_KEY_REQUIRED": (400, False),
    "DESTINATION_NOT_FOUND": (404, False),
"JOB_NOT_FOUND": (404, False),
"DEST_RULE_SELF_PROMO": (422, False),
"DEST_RULE_LINKS": (422, False),
"DEST_RULE_AI_DISCLOSURE": (422, False),
"DEST_AUTOMATION_NOT_ALLOWED": (422, False),
"CONNECTION_MISSING": (400, False),
"IDEMPOTENCY_KEY_REUSED": (409, False),
"INTERNAL_ERROR": (500, False),
}


def make_error(code, message, details=None):
    status, retryable = CODE_INFO[code]
    return AppError(code, message, status, retryable, details)
