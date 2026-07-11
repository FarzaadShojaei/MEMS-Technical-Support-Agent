from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    with patch("app.main.store.count", return_value=42):
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["indexed_chunks"] == 42


def test_ask_rejects_when_index_empty():
    with patch("app.main.store.count", return_value=0):
        resp = client.post("/ask", json={"question": "What is WHO_AM_I?"})
    assert resp.status_code == 503


def test_ask_validates_input():
    resp = client.post("/ask", json={"question": "hi"})  # too short
    assert resp.status_code == 422
