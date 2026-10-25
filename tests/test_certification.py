import pathlib

import pytest
from fastapi.testclient import TestClient

from app import catalogue, certification, config
from app.connectors import get_connector
from app.connectors import lemmy as lemmy_mod
from app.connectors.discourse import DiscourseConnector
from app.connectors.ghost import ghost_token
from app.db import get_conn
from app.errors import AppError
from app.main import app
from app.mock_platforms import STATE, mock_app, reset_state

client = TestClient(app)
URLS = {"discourse": "https://forum.example", "devto": "https://dev.to",
        "webhook": "https://partner.example/hook", "lemmy": "http://localhost:8536/c/testcomm",
        "ghost": "http://localhost:2368", "assisted": "https://forum.example"}


@pytest.fixture(autouse=True)
def fresh():
    reset_state()
    lemmy_mod.clear_auth_cache()


def make_dest(key, **over):
    row = {"name": f"{key} test", "url": URLS[key], "platform_key": key, "connector_key": key}
    row.update(over)
    status, dest_id = catalogue.add_destination(row)
    assert status == "created", dest_id
    return dest_id


def live_posts():
    return [p for p in STATE["posts"].values() if not p.get("deleted")]


def alerts():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM alerts").fetchall()
    conn.close()
    return rows


@pytest.mark.parametrize("key,level", [("discourse", "L3"), ("devto", "L3"), ("lemmy", "L3"),
                                       ("ghost", "L3"), ("webhook", "L2")])
def test_connector_passes_full_certification_run(key, level):
    d = make_dest(key)
    ev = certification.certify(d)
    assert ev["result"] == "passed", ev
    assert [s["step"] for s in ev["steps"]] == ["validate", "publish", "confirm_live", "delete", "confirm_deleted"]
    assert ev["deleted_within_10_min"] is True
    assert live_posts() == []
    row = catalogue.get_destination(d)
    assert row["level"] == level and row["last_certified_at"]
    assert pathlib.Path(ev["evidence_path"]).exists()


def test_assisted_connector_certifies_at_L1():
    d = make_dest("assisted", automation_allowed="false")
    ev = certification.certify(d)
    assert ev["result"] == "passed"
    assert [s["step"] for s in ev["steps"]] == ["build_pack", "check_pack"]
    assert catalogue.get_destination(d)["level"] == "L1"


def test_renamed_api_field_fails_certification_and_demotes():
    d = make_dest("discourse")
    STATE["rename_id"] = True
    ev = certification.certify(d)
    assert ev["result"] == "failed" and ev["failed_step"] == "publish"
    assert ev["error_code"] == "PLATFORM_RESPONSE_CHANGED"
    assert ev["cleanup"]["status"] == "post_id_unknown"        # we are told a test post may be left over
    row = catalogue.get_destination(d)
    assert row["enabled"] == 0 and row["level"] == "L0"
    assert len(alerts()) >= 1

    # a demoted destination is excluded from publishing automatically
    r = client.post("/api/v1/publications", headers={"Idempotency-Key": "after-demotion"},
                    json={"destination_id": d, "post": {"title": "Hi", "body": "x"}})
    job = client.get(f"/api/v1/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "failed" and job["error"]["code"] == "DESTINATION_NOT_FOUND"

    # once the platform is back to normal, recertification restores it
    STATE["rename_id"] = False
    assert certification.certify(d)["result"] == "passed"
    assert catalogue.get_destination(d)["enabled"] == 1


def test_temporary_outage_is_inconclusive_and_not_demoted():
    d = make_dest("devto")
    STATE["fail_next"] = [503]
    ev = certification.certify(d)
    assert ev["result"] == "inconclusive" and ev["error_code"] == "PLATFORM_UNAVAILABLE"
    assert catalogue.get_destination(d)["enabled"] == 1


def test_expired_token_fails_and_demotes():
    d = make_dest("devto")
    STATE["fail_next"] = [401]
    ev = certification.certify(d)
    assert ev["error_code"] == "CONNECTION_AUTH_EXPIRED"
    assert catalogue.get_destination(d)["enabled"] == 0


def test_failed_check_still_deletes_the_test_post(monkeypatch):
    monkeypatch.setattr(DiscourseConnector, "get_status",
                        lambda self, pid, conn: {"status": "deleted", "live_url": None})
    d = make_dest("discourse")
    ev = certification.certify(d)
    assert ev["result"] == "failed" and ev["failed_step"] == "confirm_live"
    assert ev["cleanup"]["status"] == "deleted"
    assert live_posts() == []


def test_real_mode_refuses_hosts_that_are_not_allow_listed(monkeypatch):
    monkeypatch.setattr(config, "SIMULATION_MODE", False)
    monkeypatch.setenv("CONN_DISCOURSE", '{"base_url": "https://some-real-forum.example", "api_key": "x"}')
    d = make_dest("discourse")
    with pytest.raises(AppError) as e:
        certification.certify(d)
    assert e.value.code == "CERT_TARGET_NOT_ALLOWED"


def test_certification_runs_as_a_job_and_evidence_has_no_secrets():
    d = make_dest("webhook")
    r = client.post("/api/v1/certifications", json={"destination_id": d}, headers={"Idempotency-Key": "c1"})
    assert r.status_code == 202
    job = client.get(f"/api/v1/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "succeeded" and job["result"]["result"] == "passed"
    text = pathlib.Path(job["result"]["evidence_path"]).read_text()
    assert "demo-secret" not in text and "sim-key" not in text
    assert len(client.get(f"/api/v1/destinations/{d}/certifications").json()["items"]) == 1


def test_lemmy_bad_login_maps_to_auth_expired():
    c = get_connector("lemmy", client=TestClient(mock_app))
    conn = {"base_url": "http://mock/lemmy", "username": "bad-user", "password": "expired"}
    with pytest.raises(AppError) as e:
        c.publish({"title": "t"}, {"url": URLS["lemmy"]}, conn, "k")
    assert e.value.code == "CONNECTION_AUTH_EXPIRED"


def test_lemmy_community_name_is_read_from_url():
    assert lemmy_mod.community_name("http://localhost:8536/c/testcomm") == "testcomm"
    assert lemmy_mod.community_name("http://localhost:8536/") is None


def test_ghost_token_is_a_valid_signed_jwt():
    import jwt
    secret = "00" * 32
    token = ghost_token("abc123:" + secret)
    assert jwt.get_unverified_header(token)["kid"] == "abc123"
    payload = jwt.decode(token, bytes.fromhex(secret), algorithms=["HS256"], audience="/admin/")
    assert payload["exp"] > payload["iat"]