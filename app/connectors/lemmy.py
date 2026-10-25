import re

from app.connectors.base import Connector
from app.errors import AppError, make_error

_JWT: dict = {}   # (base_url, username) -> token, so we don't log in on every call
AUTH_ERRORS = {"not_logged_in", "incorrect_login"}


def clear_auth_cache():
    _JWT.clear()


def community_name(url: str | None):
    """http://host/c/testcomm -> testcomm"""
    m = re.search(r"/c/([^/@?#]+)", url or "")
    return m.group(1) if m else None


class LemmyConnector(Connector):
    key = "lemmy"

    def _base(self, connection):
        return connection.get("base_url", "").rstrip("/")

    def _raise_lemmy_error(self, resp):
        try:
            err = resp.json().get("error", "")
        except ValueError:
            err = ""
        if err in AUTH_ERRORS:
            _JWT.clear()
            raise make_error("CONNECTION_AUTH_EXPIRED", "Lemmy login is invalid or expired.",
                             {"platform_error": err})
        if err == "rate_limit_error":
            raise make_error("PLATFORM_RATE_LIMIT", "Lemmy rate limit reached.",
                             {"platform_error": err, "retry_after_s": resp.headers.get("Retry-After")})
        raise make_error("PLATFORM_CONTENT_REJECTED", f"Lemmy refused the request: {err or 'unknown'}",
                         {"platform_error": err})

    def _token(self, connection):
        base = self._base(connection)
        cache_key = (base, connection.get("username"))
        if cache_key not in _JWT:
            resp = self._request("POST", f"{base}/api/v3/user/login", allow=(400,),
                                 json={"username_or_email": connection.get("username", ""),
                                       "password": connection.get("password", "")})
            if resp.status_code == 400:
                self._raise_lemmy_error(resp)
            _JWT[cache_key] = resp.json()["jwt"]
        return _JWT[cache_key]

    def _call(self, method, connection, path, **kwargs):
        headers = {"Authorization": f"Bearer {self._token(connection)}"}
        resp = self._request(method, f"{self._base(connection)}/api/v3{path}",
                             allow=(400,), headers=headers, **kwargs)
        if resp.status_code == 400:
            self._raise_lemmy_error(resp)
        return resp

    def _community_id(self, connection, name):
        resp = self._call("GET", connection, "/community", params={"name": name})
        return resp.json()["community_view"]["community"]["id"]

    def publish(self, rendition, destination, connection, idempotency_key):
        name = community_name(destination.get("url"))
        if not name:
            raise make_error("DEST_SPEC_VIOLATION", "Destination url must look like https://host/c/<community>.",
                             {"url": destination.get("url")})
        payload = {"name": rendition["title"], "community_id": self._community_id(connection, name)}
        if rendition.get("body"):
            payload["body"] = rendition["body"]
        if rendition.get("canonical_url"):
            payload["url"] = rendition["canonical_url"]
        post = self._call("POST", connection, "/post", json=payload).json()["post_view"]["post"]
        return {"platform_post_id": str(post["id"]),
                "live_url": f"{self._base(connection)}/post/{post['id']}",
                "status": "published"}

    def get_status(self, platform_post_id, connection):
        try:
            resp = self._call("GET", connection, "/post", params={"id": platform_post_id})
        except AppError as err:
            if err.details.get("platform_error") == "couldnt_find_post":
                return {"status": "deleted", "live_url": None}
            raise
        post = resp.json()["post_view"]["post"]
        if post.get("deleted") or post.get("removed"):
            return {"status": "deleted", "live_url": None}
        return {"status": "published", "live_url": f"{self._base(connection)}/post/{post['id']}"}

    def delete(self, platform_post_id, connection):
        self._call("POST", connection, "/post/delete",
                   json={"post_id": int(platform_post_id), "deleted": True})
        return {"deleted": True}