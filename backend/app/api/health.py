import os
from fastapi import APIRouter, Request
from ..config import get_settings

router = APIRouter()

@router.get("/health")
def health(request: Request) -> dict:
    tasks = getattr(request.app.state, "worker_tasks", {})
    settings = get_settings()
    enabled = {
        "inbox_poller": bool(settings.user_email and settings.user_email_app_password.get_secret_value()),
        "deadline_ticker": True,
        "demo_bot": bool(settings.demo_mode and settings.send_enabled and settings.demo_company_email and settings.demo_company_app_password.get_secret_value()),
    }
    return {
        "status": "ok",
        "instance_id": getattr(request.app.state, "instance_id", None),
        "pid": os.getpid(),
        "workers": {name: {"running": bool((task := tasks.get(name)) and not task.done()), "enabled": active}
                    for name, active in enabled.items()},
    }
