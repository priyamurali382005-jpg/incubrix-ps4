import pytest
from fastapi.testclient import TestClient

from app import config
from app.connectors import get_connector
from app.errors import AppError
from app.main import app
from app.mock_platforms import mock_app, reset_state

BASE = "http://mock"
REND = {
    "title": "Five Python Tips",
    "body": "Body text",
    "links": ["https://x.com"],
}

CONNECTIONS = {
    "discourse": {"base_url": f"{BASE}/discourse", "api_key": "k"},
    "devto": {"base_url": f"{BASE}/devto", "api_key": "k"},
    "webhook": {
        "base_url": f"{BASE}/webhook/receive",
        "secret": "demo-secret",
    },
}


@pytest.fixture
def mock():
    reset_state()
    return TestClient(mock_app)


@pytest.mark.parametrize("key", list(CONNECTIONS))
def test_publish_status_delete_lifecycle(mock, key):
    connector = get_connector(key, client=mock)
    connection = CONNECTIONS[key]

    result = connector.publish(REND, {}, connection, "idem-1")
    assert result["status"] == "published"
    assert result["live_url"]

    status = connector.get_status(
        result["platform_post_id"], connection
    )
    assert status["status"] == "published"

    assert connector.delete(
        result["platform_post_id"], connection
    ) == {"deleted": True}

    assert connector.get_status(
        result["platform_post_id"], connection
    )["status"] == "deleted"


def test_expired_token_maps_to_auth_expired(mock):
    connector = get_connector("discourse", client=mock)

    with pytest.raises(AppError) as error:
        connector.publish(
            REND,
            {},
            {**CONNECTIONS["discourse"], "api_key": "expired"},
            "key-1",
        )

    assert error.value.code == "CONNECTION_AUTH_EXPIRED"


def test_429_maps_to_rate_limit_with_retry_after(mock):
    mock.post("/_control", json={"fail_next": [429]})

    with pytest.raises(AppError) as error:
        get_connector("devto", client=mock).publish(
            REND, {}, CONNECTIONS["devto"], "key-2"
        )

    assert error.value.code == "PLATFORM_RATE_LIMIT"
    assert error.value.retryable is True
    assert error.value.details["retry_after_s"] == "30"


def test_server_error_maps_to_unavailable(mock):
    mock.post("/_control", json={"fail_next": [503]})

    with pytest.raises(AppError) as error:
        get_connector("discourse", client=mock).publish(
            REND, {}, CONNECTIONS["discourse"], "key-3"
        )

    assert error.value.code == "PLATFORM_UNAVAILABLE"


def test_rejected_content_maps_to_content_rejected(mock):
    long_rendition = {"title": "x" * 300, "body": "Body text"}

    with pytest.raises(AppError) as error:
        get_connector("discourse", client=mock).publish(
            long_rendition, {}, CONNECTIONS["discourse"], "key-4"
        )

    assert error.value.code == "PLATFORM_CONTENT_REJECTED"


def test_validate_reports_field_level_reasons():
    result = get_connector("devto").validate(
        {"title": "x" * 200, "body": "Body text"}, {}, {}
    )

    assert result["ok"] is False
    assert result["violations"][0]["field"] == "title"


def test_wrong_webhook_secret_is_rejected(mock):
    bad_connection = {
        **CONNECTIONS["webhook"],
        "secret": "wrong",
    }

    with pytest.raises(AppError) as error:
        get_connector("webhook", client=mock).publish(
            REND, {}, bad_connection, "key-5"
        )

    assert error.value.code == "CONNECTION_AUTH_EXPIRED"


def test_assisted_pack_includes_destination_rules():
    destination = {
        "url": "https://forum.example",
        "rules_url": "https://forum.example/rules",
        "frequency_cap_per_week": 1,
        "self_promo_allowed": 0,
        "link_policy": "none",
        "disclosure_required": 1,
    }

    pack = get_connector("assisted").build_assist_pack(
        REND, destination
    )
    checklist = " ".join(pack["checklist"])

    assert "NOT allowed" in checklist
    assert "AI-content" in checklist
    assert pack["deep_link"]


def test_kill_switch(monkeypatch):
    monkeypatch.setattr(config, "DISABLED_CONNECTORS", {"devto"})

    with pytest.raises(AppError) as error:
        get_connector("devto")

    assert error.value.code == "CONNECTOR_DISABLED"


def test_contract_route_over_http():
    client = TestClient(app)

    response = client.post(
        "/connector/v1/assisted/build_assist_pack",
        json={
            "rendition": REND,
            "destination": {"url": "https://forum.example"},
        },
    )
    assert response.status_code == 200
    assert "checklist" in response.json()

    response = client.post(
        "/connector/v1/nope/publish",
        json={},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONNECTOR_NOT_FOUND"

    response = client.post(
        "/connector/v1/assisted/fetch_metrics",
        json={},
    )
    assert response.json()["error"]["code"] == "METHOD_NOT_SUPPORTED"
