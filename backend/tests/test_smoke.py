from fastapi.testclient import TestClient
from sqlalchemy import inspect
from backend.app.config import Settings
from backend.app.main import create_app


def test_health_and_database(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", frontend_dist=tmp_path / "no-export"))
    with TestClient(app,base_url='https://testserver') as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok" and health["instance_id"] and health["pid"] > 0
        assert set(health["workers"]) == {"inbox_poller", "deadline_ticker", "demo_bot"}
        assert all(worker["running"] for worker in health["workers"].values())
        assert health["workers"]["inbox_poller"]["enabled"] is False
        assert client.get("/api/missing").status_code == 404
        assert set(inspect(app.state.engine).get_table_names()) == {
            "case", "evidence", "message", "event", "deadline", "llm_calls", "settings", "userprofile",
        }
