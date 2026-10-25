import pathlib
import re
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app import config
from app.errors import make_error


def _clean(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120]


def _s3(endpoint: str):
    return boto3.client(
        "s3", endpoint_url=endpoint or None, aws_access_key_id=config.S3_ACCESS_KEY,
        aws_secret_access_key=config.S3_SECRET_KEY, region_name=config.S3_REGION,
        config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10,
                      retries={"max_attempts": 2}))


def put(name: str, data: bytes, content_type: str = "application/json") -> dict:
    """Saves an output file and returns {"key", "url", "backend"}. The url is a download link."""
    key = f"{uuid.uuid4().hex[:12]}-{_clean(name)}"
    if config.STORAGE_BACKEND == "s3":
        return _put_s3(key, data, content_type)
    folder = pathlib.Path(config.FILES_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / key).write_bytes(data)
    return {"key": key, "url": f"{config.PUBLIC_BASE_URL}/api/v1/files/{key}", "backend": "local"}


def _put_s3(key, data, content_type):
    try:
        client = _s3(config.S3_ENDPOINT)
        try:
            client.head_bucket(Bucket=config.S3_BUCKET)
        except ClientError:
            client.create_bucket(Bucket=config.S3_BUCKET)
        client.put_object(Bucket=config.S3_BUCKET, Key=key, Body=data, ContentType=content_type)
        # presigning is a local calculation, so it can use the address a browser can reach
        url = _s3(config.S3_PUBLIC_ENDPOINT or config.S3_ENDPOINT).generate_presigned_url(
            "get_object", Params={"Bucket": config.S3_BUCKET, "Key": key}, ExpiresIn=config.S3_URL_EXPIRES_S)
    except (BotoCoreError, ClientError) as exc:
        raise make_error("STORAGE_UNAVAILABLE", f"Object storage error: {type(exc).__name__}")
    return {"key": key, "url": url, "backend": "s3"}


def read_local(key: str) -> pathlib.Path:
    path = pathlib.Path(config.FILES_DIR) / pathlib.Path(key).name   # .name blocks path tricks
    if not path.is_file():
        raise make_error("FILE_NOT_FOUND", "No such file.")
    return path
