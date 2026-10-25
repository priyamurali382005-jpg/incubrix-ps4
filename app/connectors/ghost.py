
import html
import time

import jwt

from app.connectors.base import Connector
from app.errors import make_error


def ghost_token(admin_key: str) -> str:
    try:
        key_id, secret = admin_key.split(":")
        secret_bytes = bytes.fromhex(secret)
    except (ValueError, AttributeError):
        raise make_error(
            "CONNECTION_MISSING",
            "Ghost admin_key must look like <id>:<hex secret>.",
        )

    now = int(time.time())

    return jwt.encode(
        {"iat": now, "exp": now + 300, "aud": "/admin/"},
        secret_bytes,
        algorithm="HS256",
        headers={"kid": key_id},
    )


def to_html(text: str) -> str:
    paragraphs = [
        paragraph.strip()
        for paragraph in (text or "").split("\n\n")
        if paragraph.strip()
    ]
    return "".join(
        f"<p>{html.escape(paragraph)}</p>"
        for paragraph in paragraphs
    )


class GhostConnector(Connector):
    key = "ghost"
    API = "/ghost/api/admin"

    def _base(self, connection):
        return connection.get("base_url", "").rstrip("/")

    def _headers(self, connection):
        return {
            "Authorization": (
                f"Ghost {ghost_token(connection.get('admin_key', ''))}"
            ),
            "Accept-Version": "v5.0",
        }

    def publish(self, rendition, destination, connection, idempotency_key):
        post = {
            "title": rendition["title"],
            "html": to_html(rendition.get("body", "")),
            "status": "published",
        }

        if rendition.get("canonical_url"):
            post["canonical_url"] = rendition["canonical_url"]

        resp = self._request(
            "POST",
            f"{self._base(connection)}{self.API}/posts/?source=html",
            headers=self._headers(connection),
            json={"posts": [post]},
        )

        try:
            created = resp.json()["posts"][0]
        except (ValueError, KeyError, IndexError, TypeError):
            raise make_error(
                "PLATFORM_RESPONSE_CHANGED",
                "Ghost publish response did not contain a post.",
            )

        return {
            "platform_post_id": str(created["id"]),
            "live_url": created["url"],
            "status": "published",
        }

    def get_status(self, platform_post_id, connection):
        resp = self._request(
            "GET",
            f"{self._base(connection)}{self.API}/posts/{platform_post_id}/",
            allow=(404,),
            headers=self._headers(connection),
        )

        if resp.status_code == 404:
            return {"status": "deleted", "live_url": None}

        try:
            post = resp.json()["posts"][0]
        except (ValueError, KeyError, IndexError, TypeError):
            raise make_error(
                "PLATFORM_RESPONSE_CHANGED",
                "Ghost status response did not contain a post.",
            )

        return {
            "status": (
                "published" if post["status"] == "published"
                else post["status"]
            ),
            "live_url": post["url"],
        }

    def delete(self, platform_post_id, connection):
        self._request(
            "DELETE",
            f"{self._base(connection)}{self.API}/posts/{platform_post_id}/",
            allow=(404,),
            headers=self._headers(connection),
        )

        return {"deleted": True}
