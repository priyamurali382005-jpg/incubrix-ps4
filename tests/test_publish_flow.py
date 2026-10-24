import logging

import pytest
from fastapi.testclient import TestClient

from app import catalogue, workflow
from app.logging_utils import redact
from app.main import app
from app.mock_platforms import STATE, reset_state

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    reset_state()
    workflow.reset_state()
    sleeps = []
    monkeypatch.setattr(workflow, "_sleep", sleeps.append)  # record waits instead of waiting
    return sleeps


def make_dest(connector="webhook", **over):
    row = {"name": "Test", "url": f"https://{connector}.example", "platform_key": connector,
           "connector_key": connector}
    row.update(over)  # note: values must be strings, like CSV cells
    status, dest_id = catalogue.add_destination(row)
    assert status == "created", dest_id
    return dest_id


def publish(dest_id, key, **post):
    body = {"destination_id": dest_id, "post": {"title": "Five Python Tips", "body": "Body", **post}}
    r = client.post("/api/v1/publications", json=body, headers={"Idempotency-Key": key})
    assert r.status_code == 202
    return r.json()["job_id"], client.get(f"/api/v1/jobs/{r.json()['job_id']}").json()


def test_happy_path_returns_202_and_job_succeeds():
    _, job = publish(make_dest(), "k1")
    assert job["status"] == "succeeded" and job["progress"] == 100
    assert job["result"]["live_url"]
    assert len(STATE["posts"]) == 1


def test_missing_idempotency_key_is_rejected():
    r = client.post("/api/v1/publications", json={"destination_id": 1, "post": {"title": "x"}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_same_key_twice_gives_same_job_and_one_post():
    d = make_dest()
    first, _ = publish(d, "same")
    second, _ = publish(d, "same")
    assert first == second
    assert len(STATE["posts"]) == 1


def test_same_key_different_request_is_rejected():
    d = make_dest()
    publish(d, "reuse", title="One")
    r = client.post("/api/v1/publications", headers={"Idempotency-Key": "reuse"},
                    json={"destination_id": d, "post": {"title": "Different"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_timeout_after_success_then_retry_creates_no_duplicate():
    # webhook platform creates the post, but the caller sees a 504. The retry reuses the key.
    STATE["create_then_fail"] = True
    _, job = publish(make_dest("webhook"), "timeout-1")
    assert job["status"] == "succeeded" and job["result"]["attempts"] == 2
    assert len(STATE["posts"]) == 1


def test_timeout_on_platform_without_dedup_is_not_blindly_retried():
    STATE["create_then_fail"] = True
    _, job = publish(make_dest("discourse"), "timeout-2")
    assert job["status"] == "failed"
    assert job["result"]["outcome"] == "unknown_outcome"
    assert job["error"]["details"]["outcome_unknown"] is True
    assert len(STATE["posts"]) == 1   # exactly one, never two


def test_429_waits_for_reset_time_then_succeeds(fresh):
    STATE["fail_next"] = [429]        # mock sends Retry-After: 30
    _, job = publish(make_dest("devto"), "rl-1")
    assert job["status"] == "succeeded"
    assert fresh == [30.0]


def test_second_post_inside_weekly_cap_is_rescheduled():
    d = make_dest(frequency_cap_per_week="1")
    publish(d, "cap-1")
    _, job = publish(d, "cap-2")
    assert job["status"] == "failed" and job["result"]["outcome"] == "rescheduled"
    assert job["error"]["code"] == "DEST_RULE_FREQUENCY_CAP"
    assert job["error"]["details"]["retry_after"]
    assert len(STATE["posts"]) == 1


def test_promotional_post_to_no_promo_destination_is_blocked():
    _, job = publish(make_dest(self_promo_allowed="false"), "promo-1", is_promotional=True)
    assert job["result"]["outcome"] == "blocked"
    assert job["error"]["code"] == "DEST_RULE_SELF_PROMO"
    assert len(STATE["posts"]) == 0


def test_too_long_title_is_a_spec_violation_with_field_reason():
    _, job = publish(make_dest("devto"), "long-1", title="x" * 200)
    assert job["error"]["code"] == "DEST_SPEC_VIOLATION"
    assert job["error"]["details"]["violations"][0]["field"] == "title"


def test_automation_not_allowed_blocks_api_connectors():
    _, job = publish(make_dest(automation_allowed="false"), "auto-1")
    assert job["error"]["code"] == "DEST_AUTOMATION_NOT_ALLOWED"


def test_assisted_destination_returns_pack_and_pending_status():
    d = make_dest("assisted", automation_allowed="false", self_promo_allowed="false")
    _, job = publish(d, "assist-1")
    assert job["status"] == "succeeded" and job["result"]["outcome"] == "assist_pending"
    assert any("NOT allowed" in line for line in job["result"]["pack"]["checklist"])


def test_unknown_job_is_404():
    assert client.get("/api/v1/jobs/nope").json()["error"]["code"] == "JOB_NOT_FOUND"


def test_secrets_never_appear_in_logs(caplog):
    caplog.set_level(logging.INFO)
    publish(make_dest("discourse"), "log-1")
    publish(make_dest("webhook"), "log-2")
    assert "sim-key" not in caplog.text and "demo-secret" not in caplog.text
    assert "job_id" in caplog.text


def test_redact_hides_credentials():
    assert "abc123" not in redact('{"api_key": "abc123", "Authorization": "Bearer abc123"}')