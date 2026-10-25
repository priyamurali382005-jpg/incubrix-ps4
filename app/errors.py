
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
    "PLATFORM_RESPONSE_CHANGED": (502, False),
    "CERT_TARGET_NOT_ALLOWED": (403, False),
    "CERT_CHECK_FAILED": (422, False)

}


def make_error(code, message, details=None):
    status, retryable = CODE_INFO[code]
    return AppError(code, message, status, retryable, details)

# --- phase6 additions ---

from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException

CODE_INFO.update({
    "DESTINATION_DUPLICATE": (409, False),
    "REQUEST_INVALID": (422, False),
    "NOT_FOUND": (404, False),
    "METHOD_NOT_ALLOWED": (405, False),
    "HTTP_ERROR": (400, False),
    "UNAUTHORIZED": (401, False),
    "RATE_LIMITED": (429, True),
    "FILE_NOT_FOUND": (404, False),
    "FETCH_BLOCKED": (422, False),
    "FETCH_FAILED": (502, True),
    "STORAGE_UNAVAILABLE": (503, True),
    "PAYLOAD_TOO_LARGE": (413, False),
    "SERVICE_NOT_READY": (503, True),
})


def _body(code, message, retryable=False, details=None):
    return {"error": {"code": code, "message": message, "retryable": retryable, "details": details or {}}}


def error_response(code, message, details=None):
    status, retryable = CODE_INFO[code]
    return JSONResponse(status_code=status, content=_body(code, message, retryable, details))


async def validation_error_handler(request, exc):
    return JSONResponse(status_code=422, content=_body(
        "REQUEST_INVALID", "Request body or parameters are invalid.", False,
        {"errors": jsonable_encoder(exc.errors())}))


async def http_error_handler(request, exc: StarletteHTTPException):
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(status_code=exc.status_code,
                        content=_body(code, str(exc.detail), exc.status_code in (502, 503, 504)))
