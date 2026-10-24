
import contextvars
import json
import logging
import re
import time

correlation_id = contextvars.ContextVar("correlation_id", default=None)

_SECRET = re.compile(
    r'("?(?:api[_-]?key|secret|token|authorization|password)"?\s*[:=]\s*)("[^"]*"|\S+)',
    re.IGNORECASE,
)


def redact(text: str) -> str:
    return _SECRET.sub(r'\1"***"', text)


def log_event(level: str, message: str, job_id: str | None = None, **fields):
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "level": level,
        "message": message,
        "job_id": job_id,
        "correlation_id": correlation_id.get(),
        **fields,
    }
    line = redact(json.dumps(record, default=str))
    logging.getLogger("incubrix").log(getattr(logging, level), line)
