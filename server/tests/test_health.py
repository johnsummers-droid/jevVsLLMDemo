from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_the_configured_origin() -> None:
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    response = client.options("/api/graphs/validate", headers=headers)
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    response = client.options("/api/graphs/validate", headers={**headers, "Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
