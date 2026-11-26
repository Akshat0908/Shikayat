import asyncio
from uuid import uuid4
from contextlib import asynccontextmanager, suppress
from collections.abc import AsyncIterator
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from .api.health import router
from .config import Settings, get_settings
from .db import build_engine, init_db
from .events import EventBus
from .privacy import COOKIE, visitor_id, visible, event_visible, retention_loop
from .models import Case
from sqlmodel import Session
from fastapi.responses import JSONResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    bus = EventBus()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = build_engine(config.database_url)
        init_db(app.state.engine)
        ping_task = asyncio.create_task(bus.ping_forever())
        from .workers import inbox_loop, deadline_loop
        from .demo.company_bot import company_loop
        app.state.instance_id = str(uuid4())
        app.state.worker_tasks = {
            'inbox_poller': asyncio.create_task(inbox_loop(app), name='inbox_poller'),
            'deadline_ticker': asyncio.create_task(deadline_loop(app), name='deadline_ticker'),
            'demo_bot': asyncio.create_task(company_loop(app), name='demo_bot'),
        }
        tasks = [*app.state.worker_tasks.values(), asyncio.create_task(retention_loop(app), name='retention')]

        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            ping_task.cancel()
            with suppress(asyncio.CancelledError):
                await ping_task
            app.state.engine.dispose()

    app = FastAPI(title="Shikayat", lifespan=lifespan)
    app.state.pending_cases = {}
    app.state.events = bus
    app.state.config = config
    @app.middleware("http")
    async def isolate_cases(request: Request, call_next):
        request.state.visitor_id = visitor_id(request)
        parts = request.url.path.strip('/').split('/')
        if len(parts) >= 3 and parts[:2] == ['api', 'cases'] and parts[2] != 'sample':
            with Session(request.app.state.engine) as session:
                case = session.get(Case, parts[2])
                allowed = bool(case and visible(request, case))
            if not allowed:
                response = JSONResponse({'detail': 'Case not found'}, status_code=404)
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
        if request.cookies.get(COOKIE) != request.state.visitor_id:
            response.set_cookie(COOKIE, request.state.visitor_id, max_age=365*24*3600,
                                httponly=True, secure=True, samesite='lax', path='/')
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/experiment/config')
    def experiment_config() -> dict:
        # Environment keys are public SDK keys, never management credentials.
        return {'environment_id': config.flagsmith_environment_id, 'api_url': config.flagsmith_api_url or None, 'events_url': config.flagsmith_events_url or None}

    @app.get('/api/session')
    def visitor_session() -> dict:
        return {'ready': True}

    app.include_router(router, prefix="/api")
    from .api.companies import router as companies_router
    app.include_router(companies_router)
    from .api.company_cases import router as company_cases_router
    app.include_router(company_cases_router)
    from .api.admin import router as admin_router
    app.include_router(admin_router)
    from .api.cases import router as cases_router
    app.include_router(cases_router)
    from .api.drafts import router as drafts_router
    app.include_router(drafts_router)
    from .api.manual_send import router as manual_send_router
    app.include_router(manual_send_router)
    from .api.case_controls import router as controls_router
    app.include_router(controls_router)
    from .api.profile import router as profile_router
    app.include_router(profile_router)
    from .api.eval import router as eval_router
    app.include_router(eval_router)
    from .api.demo import router as demo_router
    app.include_router(demo_router)

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            async with bus.subscribe() as queue:
                yield ": connected\n\n"
                while not await request.is_disconnected():
                    message = await queue.get()
                    if event_visible(request, message):
                        yield message
        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
        })

    # API routes always take precedence over the production static export.
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unknown_api(path: str) -> None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="API route not found")

    if config.frontend_dist.is_dir():
        from fastapi.responses import FileResponse

        @app.get('/proof')
        @app.get('/proof/')
        def proof_page() -> FileResponse:
            return FileResponse(config.frontend_dist / 'proof' / 'index.html')

        app.mount("/", StaticFiles(directory=config.frontend_dist, html=True), name="frontend")
    return app


app = create_app()
