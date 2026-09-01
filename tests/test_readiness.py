from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_liveness_does_not_depend_on_database():
    from api.main import app

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_readiness_returns_200_when_database_is_online():
    from api.main import app

    with patch(
        "api.main.config.check_database_health",
        new_callable=AsyncMock,
        return_value={"status": "online"},
    ):
        response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": {"status": "online"},
    }


def test_readiness_returns_503_with_safe_database_error():
    from api.main import app

    database_status = {"status": "offline", "error": "Health check timeout"}
    with patch(
        "api.main.config.check_database_health",
        new_callable=AsyncMock,
        return_value=database_status,
    ):
        response = TestClient(app).get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": {"status": "offline"},
    }
