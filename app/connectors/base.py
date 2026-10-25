import pathlib

import httpx
import yaml

from app import config
from app.errors import make_error

MANIFEST_DIR = pathlib.Path(__file__).parent / "manifests"


def load_manifest(key: str) -> dict:
    path = MANIFEST_DIR / f"{key}.yaml"
    if not path.is_file():
        raise make_error("CONNECTOR_NOT_FOUND", f"Manifest not found for '{key}'.")
    with path.open("r", encoding="utf-8-sig") as file:
        manifest = yaml.safe_load(file)
    if not isinstance(manifest, dict):
        raise ValueError(f"Invalid connector manifest: {key}")
    return manifest


class Connector:
    key = ""

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=config.HTTP_TIMEOUT_S)
        self.manifest = load_manifest(self.key)

    def validate(self, rendition, destination, connection):
        spec = self.manifest["surfaces"][0]["spec"]
        violations = []
        title = rendition.get("title", "")
        body = rendition.get("body", "")

        if not title:
            violations.append({
                "field": "title",
                "reason": "title is required",
            })
        if len(title) > spec["title_max_chars"]:
            violations.append({
                "field": "title",
                "reason": f"{len(title)} chars, max {spec['title_max_chars']}",
            })
        if len(body) > spec["body_max_chars"]:
            violations.append({
                "field": "body",
                "reason": f"{len(body)} chars, max {spec['body_max_chars']}",
            })
        if rendition.get("links") and not spec["links_allowed"]:
            violations.append({
                "field": "links",
                "reason": "links not allowed",
            })
        accepted = set(self.manifest["surfaces"][0]["content_types"])
        for item in rendition.get("media", []):
            kind = item.get("type", "unknown")
            if kind not in accepted:
                violations.append({
                    "field": "media",
                    "reason": (
                        f"media type '{kind}' is not accepted here; "
                        f"accepted: {sorted(accepted)}"
                    ),
                })


        return {"ok": not violations, "violations": violations}

    def publish(self, rendition, destination, connection, idempotency_key):
        raise make_error("METHOD_NOT_SUPPORTED", "publish not supported")

    def get_status(self, platform_post_id, connection):
        raise make_error("METHOD_NOT_SUPPORTED", "get_status not supported")

    def delete(self, platform_post_id, connection):
        raise make_error("METHOD_NOT_SUPPORTED", "delete not supported")

    def _request(self, method, url, allow=(), **kwargs):
        try:
            response = self.client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise make_error(
                "PLATFORM_UNAVAILABLE",
                f"Could not reach platform: {type(exc).__name__}",
            ) from exc

        if response.status_code >= 400 and response.status_code not in allow:
            self._raise_mapped(response)

        return response

    def _raise_mapped(self, response):
        code = self.manifest["error_map"].get(str(response.status_code))

        if code is None:
            code = (
                "PLATFORM_UNAVAILABLE"
                if response.status_code >= 500
                else "PLATFORM_CONTENT_REJECTED"
            )

        details = {
            "platform_status": response.status_code,
            "platform_message": response.text[:300],
        }

        if code == "PLATFORM_RATE_LIMIT":
            details["retry_after_s"] = response.headers.get("Retry-After")

        raise make_error(
            code,
            f"Platform returned HTTP {response.status_code}",
            details,
        )
