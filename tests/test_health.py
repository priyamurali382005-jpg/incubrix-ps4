
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_correlation_id_is_returned():
    response = client.get(
        "/health",
        headers={"X-Correlation-Id": "abc-123"},
    )

    assert response.headers["X-Correlation-Id"] == "abc-123"
