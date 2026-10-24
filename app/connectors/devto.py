from app.connectors.base import Connector


class DevtoConnector(Connector):
    key = "devto"

    def _headers(self, connection):
        return {"api-key": connection.get("api_key", "")}

    def _base(self, connection, destination=None):
        return (
            connection.get("base_url")
            or (destination or {}).get("url")
            or "https://dev.to"
        ).rstrip("/")

    def publish(self, rendition, destination, connection, idempotency_key):
        base = self._base(connection, destination)
        article = {
            "title": rendition["title"],
            "body_markdown": rendition.get("body", ""),
            "published": True,
            "tags": rendition.get("tags", [])[:4],
        }

        if rendition.get("canonical_url"):
            article["canonical_url"] = rendition["canonical_url"]

        response = self._request(
            "POST",
            f"{base}/api/articles",
            headers=self._headers(connection),
            json={"article": article},
        )
        data = response.json()

        return {
            "platform_post_id": str(data["id"]),
            "live_url": data["url"],
            "status": "published",
        }

    def get_status(self, platform_post_id, connection):
        base = self._base(connection)
        response = self._request(
            "GET",
            f"{base}/api/articles/{platform_post_id}",
            allow=(404,),
            headers=self._headers(connection),
        )

        if response.status_code == 404:
            return {"status": "deleted", "live_url": None}

        data = response.json()
        if not data.get("published", True):
            return {"status": "deleted", "live_url": None}

        return {"status": "published", "live_url": data["url"]}

    def delete(self, platform_post_id, connection):
        # The public Dev.to API may not support deletion.
        # This implementation unpublishes the article instead.
        base = self._base(connection)
        self._request(
            "PUT",
            f"{base}/api/articles/{platform_post_id}",
            headers=self._headers(connection),
            json={"article": {"published": False}},
        )
        return {"deleted": True}
