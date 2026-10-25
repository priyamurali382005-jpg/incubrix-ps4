
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app import config
from app.errors import make_error


def check_url(url: str):
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise make_error(
            "FETCH_BLOCKED",
            "Only http(s) URLs are allowed.",
        )

    if config.ALLOW_PRIVATE_FETCH:
        return

    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise make_error(
            "FETCH_FAILED",
            "Host name could not be resolved.",
        )

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise make_error(
                "FETCH_BLOCKED",
                "URLs that point to private networks are not allowed.",
            )


def fetch_text(url: str) -> str:
    check_url(url)
    data = bytearray()

    try:
        with httpx.stream(
            "GET",
            url,
            timeout=config.HTTP_TIMEOUT_S,
            follow_redirects=False,
        ) as response:
            if response.status_code >= 400:
                raise make_error(
                    "FETCH_FAILED",
                    f"The URL returned HTTP {response.status_code}.",
                )

            for chunk in response.iter_bytes():
                data.extend(chunk)

                if len(data) > config.MAX_UPLOAD_BYTES:
                    raise make_error(
                        "PAYLOAD_TOO_LARGE",
                        "Downloaded file is too large.",
                    )

    except httpx.HTTPError as exc:
        raise make_error(
            "FETCH_FAILED",
            f"Could not download: {type(exc).__name__}",
        )

    return data.decode("utf-8-sig", errors="replace")
