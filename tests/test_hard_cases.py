import pytest
from fastapi.testclient import TestClient

from app import catalogue, workflow
from app.main import app
from app.mock_platforms import STATE, reset_state

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    reset_state()
    workflow.reset_state()
    monkeypatch.setattr(workflow, "_sleep", lambda s: None)


def dest(key, url, **over):
    row = {"name": f"{key} {url}", "url": url, "platform_key": key, "connector_key": key, **over}
    status, dest_id = catalogue.add_destination(row)
    assert status == "created", dest_id
    return dest_id


def publish(dest_id, key, **post):
    r = client.post("/api/v1/publications", headers={"Idempotency-Key": key},
                    json={"destination_id": dest_id, "post": {"title": "Hello", "body": "Body", **post}})
    return client.get(f"/api/v1/jobs/{r.json()['job_id']}").json()


def test_media_the_destination_does_not_accept_is_rejected_with_a_reason():
    job = publish(dest("lemmy", "http://localhost:8536/c/t"), "h1",
                  media=[{"type": "image", "url": "https://x.example/a.png"}])
    assert job["error"]["code"] == "DEST_SPEC_VIOLATION"
    assert job["error"]["details"]["violations"][0]["field"] == "media"
    assert STATE["posts"] == {}


def test_partner_who_revokes_permission_is_a_connection_problem_not_a_retry_loop():
    d = dest("webhook", "https://partner.example/hook")
    STATE["fail_next"] = [403]
    job = publish(d, "h2")
    assert job["error"]["code"] == "CONNECTION_AUTH_EXPIRED" and job["error"]["retryable"] is False


def test_non_english_content_survives_end_to_end():
    d = dest("discourse", "https://tamil-forum.example", language="ta")
    title = "பைதான் தொடக்கநிலை குறிப்புகள்"
    job = publish(d, "h3", title=title, body="உள்ளடக்கம்")
    assert job["status"] == "succeeded"
    assert list(STATE["posts"].values())[0]["title"] == title


def test_destination_that_requires_ai_disclosure():
    d = dest("discourse", "https://disclosure-forum.example", disclosure_required="true")
    blocked = publish(d, "h4", ai_generated=True)
    assert blocked["error"]["code"] == "DEST_RULE_AI_DISCLOSURE" and blocked["result"]["outcome"] == "blocked"
    assert publish(d, "h5", ai_generated=True, ai_disclosure_included=True)["status"] == "succeeded"


def test_messy_multilingual_csv_gets_a_row_by_row_report():
    csv_text = ("name,url,platform_key,connector_key,language\n"
                "हिंदी फोरम,https://hindi-forum.example,discourse,discourse,hi\n"
                "Hindi forum copy,http://www.HINDI-forum.example/,discourse,discourse,hi\n"
                "தமிழ் சமூகம்,https://tamil.example,lemmy,lemmy,ta\n"
                "Broken,htp:/bad,discourse,discourse,en\n"
                "No platform,https://x.example,,discourse,en\n")
    report = catalogue.import_csv(csv_text)
    assert (report["imported"], report["duplicates"], report["invalid"]) == (2, 1, 2)
    assert {e["row"] for e in report["errors"]} == {3, 5, 6}
