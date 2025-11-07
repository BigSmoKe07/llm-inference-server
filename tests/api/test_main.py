# tests/api/test_main.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app, raise_server_exceptions=True)


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint_returns_prometheus_text(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_predict_missing_api_key_returns_422(client):
    # Header is required — FastAPI returns 422 for missing required header
    response = client.post("/predict", json={"text": "hello"})
    assert response.status_code == 422


def test_predict_wrong_api_key_returns_401(client):
    response = client.post(
        "/predict",
        json={"text": "hello"},
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401


@patch("api.main.put_job")
@patch("api.main.enqueue_job")
def test_predict_success(mock_enqueue, mock_put, client):
    response = client.post(
        "/predict",
        json={"text": "I love this!"},
        headers={"X-API-Key": "test-key-abc123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # UUID4 length
    assert data["status"] == "queued"
    mock_put.assert_called_once()
    mock_enqueue.assert_called_once()


@patch("api.main.get_job", return_value=None)
def test_result_not_found_returns_404(mock_get, client):
    response = client.get("/result/nonexistent-id", headers={"X-API-Key": "test-key-abc123"})
    assert response.status_code == 404


@patch("api.main.get_job", return_value={
    "job_id": "abc-123",
    "status": "complete",
    "label": "POSITIVE",
    "score": "0.9876",
})
def test_result_complete_returns_label_and_score(mock_get, client):
    response = client.get("/result/abc-123", headers={"X-API-Key": "test-key-abc123"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert data["label"] == "POSITIVE"
    assert data["score"] == pytest.approx(0.9876, rel=1e-3)


@patch("api.main.get_job", return_value={
    "job_id": "abc-123",
    "status": "queued",
})
def test_result_pending_has_no_label(mock_get, client):
    response = client.get("/result/abc-123", headers={"X-API-Key": "test-key-abc123"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["label"] is None
