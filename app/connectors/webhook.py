import hashlib
import hmac
import json

from app.connectors.base import Connector


def sign(secret: str, body: bytes) -> str:
    signature = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return "sha256=" + signature


class WebhookConnector(Connector):
    key = "webhook"

    def _base(self, connection, destination=None):
        return (
            connection.get("base_url")
            or (destination or {}).get("url", "")
        ).rstrip("/")

    def _headers(self, connection, body: bytes, extra=None):
        headers = {
            "X-IncuBrix-Signature": sign(
                connection.get("secret", ""),
                body,
            ),
            "Content-Type": "application/json",
        }
        headers.update(extra or {})
        return headers

    def publish(self, rendition, destination, connection, idempotency_key):
        body = json.dumps(
            rendition,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        response = self._request(
            "POST",
            self._base(connection, destination),
            content=body,
            headers=self._headers(
                connection,
                body,
                {"Idempotency-Key": idempotency_key},
            ),
        )
        data = response.json()

        return {
            "platform_post_id": str(data["id"]),
            "live_url": data.get("url"),
            "status": "published",
        }

    def get_status(self, platform_post_id, connection):
        response = self._request(
            "GET",
            f"{self._base(connection)}/{platform_post_id}",
            allow=(404,),
            headers=self._headers(connection, b""),
        )

        if response.status_code == 404:
            return {"status": "deleted", "live_url": None}

        return {
            "status": "published",
            "live_url": response.json().get("url"),
        }

    def delete(self, platform_post_id, connection):
        self._request(
            "DELETE",
            f"{self._base(connection)}/{platform_post_id}",
            allow=(404,),
            headers=self._headers(connection, b""),
        )
        return {"deleted": True}
