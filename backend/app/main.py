import asyncio
from contextlib import asynccontextmanager, suppress
from collections.abc import AsyncIterator
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from .api.health import router
from .config import Settings, get_settings
from .db import build_engine, init_db
from .events import EventBus


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
        tasks=[asyncio.create_task(worker(app)) for worker in (inbox_loop,deadline_loop,company_loop)]
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
    app.state.events = bus
    app.state.config = config
    app.include_router(router, prefix="/api")
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
                    yield await queue.get()
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
