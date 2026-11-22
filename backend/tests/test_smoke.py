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


def test_evaluator_simulation_is_local_and_requires_admin(tmp_path, monkeypatch):
    from backend.app.api import demo
    from backend.app.models import Case, Message
    from sqlmodel import Session, select
    config=Settings(database_url=f"sqlite:///{tmp_path / 'evaluator.db'}",admin_passcode='local-test',send_enabled=False,demo_mode=True,user_email='',user_email_app_password='',demo_company_email='',demo_company_app_password='')
    monkeypatch.setattr(demo,'get_settings',lambda:config)
    app=create_app(config)
    with TestClient(app,base_url='https://testserver') as client:
        with Session(app.state.engine) as session:
            case=Case(title='sample',company_id='shopkart',owner_id='owner',facts_json={'demo_sample':True})
            session.add(case);session.commit();case_id=case.id
        assert client.post('/api/demo/start',json={'case_id':case_id}).status_code==403
        assert client.post('/api/admin/login',json={'passcode':'local-test'}).status_code==200
        response=client.post('/api/demo/start',json={'case_id':case_id})
        assert response.status_code==200 and response.json()=={'status':'simulation_started','sent':False}
        with Session(app.state.engine) as session:
            message=session.exec(select(Message).where(Message.case_id==case_id)).one()
            assert message.to.endswith('@example.invalid') and 'no email was sent' in message.body_text
        assert client.post('/api/demo/start',json={'case_id':case_id}).status_code==409
