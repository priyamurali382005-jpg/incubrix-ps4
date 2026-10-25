
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.connectors import get_connector
from app.errors import make_error

router = APIRouter(prefix="/connector/v1")


class CallIn(BaseModel):
    rendition: dict = Field(default_factory=dict)
    destination: dict = Field(default_factory=dict)
    connection: dict = Field(default_factory=dict)
    idempotency_key: str | None = None
    platform_post_id: str | None = None
    since: str | None = None


METHODS = {
    "validate": None,
    "publish": "publish",
    "get_status": "status",
    "delete": "delete",
    "build_assist_pack": "build_assist_pack",
    "fetch_metrics": "metrics",
    "refresh_auth": "refresh_auth",
}


@router.post("/{connector_key}/{method}")
def call_connector(
    connector_key: str,
    method: str,
    b: CallIn,
    idempotency_key: str | None = Header(default=None),
):
    connector = get_connector(connector_key)

    if method not in METHODS:
        raise make_error(
            "METHOD_NOT_SUPPORTED",
            f"Unknown method '{method}'.",
        )

    needed = METHODS[method]
    if needed and needed not in connector.manifest["capabilities"]:
        raise make_error(
            "METHOD_NOT_SUPPORTED",
            f"'{connector_key}' does not support {method}.",
        )

    if method == "validate":
        return connector.validate(
            b.rendition,
            b.destination,
            b.connection,
        )

    if method == "publish":
        key = b.idempotency_key or idempotency_key

        if not key:
            raise make_error(
                "IDEMPOTENCY_KEY_REQUIRED",
                "publish needs idempotency_key.",
            )

        return connector.publish(
            b.rendition,
            b.destination,
            b.connection,
            key,
        )

    if method == "get_status":
        if not b.platform_post_id:
            raise make_error(
                "METHOD_NOT_SUPPORTED",
                "get_status requires platform_post_id.",
            )

        return connector.get_status(
            b.platform_post_id,
            b.connection,
        )

    if method == "delete":
        if not b.platform_post_id:
            raise make_error(
                "METHOD_NOT_SUPPORTED",
                "delete requires platform_post_id.",
            )

        return connector.delete(
            b.platform_post_id,
            b.connection,
        )

    if method == "build_assist_pack":
        return connector.build_assist_pack(
            b.rendition,
            b.destination,
        )

    raise make_error(
        "METHOD_NOT_SUPPORTED",
        f"{method} is not implemented yet.",
    )
