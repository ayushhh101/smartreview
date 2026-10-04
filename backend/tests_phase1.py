from fastapi.testclient import TestClient
from backend.main import app

c = TestClient(app)

def test_health_reports_db_state():
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["mongodb"] in ("up", "down")

def test_overview_fails_clearly_without_db():
    r = c.get("/api/stats/overview")
    assert r.status_code in (200, 503)
    if r.status_code == 503:
        assert r.json()["error"] == "database_unavailable"
