from app.connectors.base import Connector


class DiscourseConnector(Connector):
    key = "discourse"

    def _headers(self, connection):
        return {
            "Api-Key": connection.get("api_key", ""),
            "Api-Username": connection.get("username", "system"),
        }

    def _base(self, connection, destination=None):
        return (
            connection.get("base_url")
            or (destination or {}).get("url", "")
        ).rstrip("/")

    def publish(self, rendition, destination, connection, idempotency_key):
        base = self._base(connection, destination)
        response = self._request(
            "POST",
            f"{base}/posts.json",
            headers=self._headers(connection),
            json={
                "title": rendition["title"],
                "raw": rendition.get("body", ""),
            },
        )
        data = response.json()

        return {
            "platform_post_id": str(data["id"]),
            "live_url": f"{base}/t/{data['topic_slug']}/{data['topic_id']}",
            "status": "published",
        }

    def get_status(self, platform_post_id, connection):
        base = self._base(connection)
        response = self._request(
            "GET",
            f"{base}/posts/{platform_post_id}.json",
            allow=(404, 410),
            headers=self._headers(connection),
        )

        if response.status_code in (404, 410):
            return {"status": "deleted", "live_url": None}

        data = response.json()
        return {
            "status": "published",
            "live_url": f"{base}/t/{data['topic_slug']}/{data['topic_id']}",
        }

    def delete(self, platform_post_id, connection):
        base = self._base(connection)
        self._request(
            "DELETE",
            f"{base}/posts/{platform_post_id}.json",
            allow=(404, 410),
            headers=self._headers(connection),
        )
        return {"deleted": True}
