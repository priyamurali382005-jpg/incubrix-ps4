import json

import pytest
from fastapi.testclient import TestClient

from app import catalogue, config, fetch, storage
from app.connections import get_connection
from app.errors import AppError
from app.main import app
from app.mock_platforms import reset_state

client = TestClient(app)
CSV = "name,url,platform_key,connector_key\nForum A,https://forum-a.example,discourse,discourse\n"


@pytest.fixture(autouse=True)
def fresh():
    reset_state()


def post(path, key, **kw):
    return client.post(path, headers={"Idempotency-Key": key}, **kw)


def test_token_protects_api_but_not_health(monkeypatch):
    monkeypatch.setattr(config, "API_TOKEN", "s3cret-token")
    assert client.get("/health").status_code == 200
    r = client.get("/api/v1/destinations")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    assert client.get("/api/v1/destinations", headers={"X-API-Key": "s3cret-token"}).status_code == 200
    assert client.get("/api/v1/destinations", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200
    assert client.get("/api/v1/destinations", headers={"X-API-Key": "wrong"}).status_code == 401


def test_rate_limit_returns_429_with_reset_time(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 3)
    assert [client.get("/api/v1/destinations").status_code for _ in range(4)] == [200, 200, 200, 429]
    r = client.get("/api/v1/destinations")
    assert r.json()["error"]["code"] == "RATE_LIMITED" and r.headers["Retry-After"]


def test_create_destination_is_idempotent():
    body = {"name": "A", "url": "https://a.example", "platform_key": "discourse", "connector_key": "discourse"}
    r1, r2 = post("/api/v1/destinations", "d1", json=body), post("/api/v1/destinations", "d1", json=body)
    assert r1.status_code == 201 and r1.json() == r2.json()
    assert len(catalogue.list_destinations()) == 1
    r3 = post("/api/v1/destinations", "d1", json={**body, "name": "B"})
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    r4 = client.post("/api/v1/destinations", json=body)
    assert r4.status_code == 400 and r4.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_framework_errors_use_the_standard_format():
    r = post("/api/v1/publications", "v1", json={"post": {}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REQUEST_INVALID"
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_csv_upload_and_url_import(monkeypatch):
    r = client.post("/api/v1/destinations/import/upload", headers={"Idempotency-Key": "u1"},
                    files={"file": ("d.csv", CSV.encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["imported"] == 1
    monkeypatch.setattr(fetch, "fetch_text", lambda url: CSV.replace("forum-a", "forum-b"))
    r = post("/api/v1/destinations/import/url", "u2", json={"csv_url": "https://files.example/d.csv"})
    assert r.json()["imported"] == 1


def test_private_addresses_are_not_fetched():
    for bad in ("http://127.0.0.1:8000/x", "file:///etc/passwd"):
        with pytest.raises(AppError) as e:
            fetch.check_url(bad)
        assert e.value.code == "FETCH_BLOCKED"


def test_local_storage_roundtrip():
    stored = storage.put("hello.txt", b"hi", "text/plain")
    r = client.get(stored["url"])
    assert r.status_code == 200 and r.content == b"hi"
    assert client.get("/api/v1/files/missing.txt").json()["error"]["code"] == "FILE_NOT_FOUND"


def _dest(**over):
    row = {"name": "Hook", "url": "https://partner.example/hook", "platform_key": "webhook",
           "connector_key": "webhook", **over}
    status, dest_id = catalogue.add_destination(row)
    assert status == "created"
    return dest_id


def _job(dest_id, key, **post_fields):
    r = post("/api/v1/publications", key, json={"destination_id": dest_id,
                                                "post": {"title": "Hi", "body": "x", **post_fields}})
    return client.get(f"/api/v1/jobs/{r.json()['job_id']}").json()


def test_every_job_has_a_manifest_even_when_blocked():
    ok = _job(_dest(), "m1")
    m = ok["result"]["manifest"]
    assert m["providers"][0]["key"] == "webhook" and m["cost_estimate"]["amount"] == 0
    assert "timings" in m and "warnings" in m and m["ai_used"] is False
    blocked = _job(_dest(name="NoPromo", url="https://np.example", self_promo_allowed="false"), "m2",
                   is_promotional=True)
    assert blocked["result"]["outcome"] == "blocked" and blocked["result"]["manifest"]["warnings"]


def test_connections_can_come_from_a_mounted_file(monkeypatch, tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"lemmy": {"base_url": "http://lemmy:8536", "username": "admin", "password": "x"}}))
    monkeypatch.setattr(config, "SIMULATION_MODE", False)
    monkeypatch.setattr(config, "CONN_FILE", str(f))
    for name in ("CONN_1", "CONN_LEMMY", "CONN_GHOST"):
        monkeypatch.delenv(name, raising=False)
    assert get_connection({"id": 1, "connector_key": "lemmy"})["base_url"] == "http://lemmy:8536"
    with pytest.raises(AppError) as e:
        get_connection({"id": 1, "connector_key": "ghost"})
    assert e.value.code == "CONNECTION_MISSING"

import pathlib
import yaml


def test_openapi_yaml_matches_the_running_service():
    committed = yaml.safe_load(pathlib.Path("openapi.yaml").read_text(encoding="utf-8"))
    live = yaml.safe_load(yaml.safe_dump(app.openapi(), sort_keys=False))
    assert committed["openapi"].startswith("3.1")
    assert committed == live, "Run: python -m scripts.export_openapi"
