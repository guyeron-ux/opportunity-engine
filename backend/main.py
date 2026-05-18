import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.api.routes import router

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    # Ensure data directories exist
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.backups_dir.mkdir(parents=True, exist_ok=True)

    # Init orchestrator + scheduler
    from backend.agents.orchestrator import Orchestrator
    from backend.api.websocket import ws_manager
    from backend.scheduler import create_scheduler

    orchestrator = Orchestrator(ws_manager=ws_manager)
    _scheduler = create_scheduler(orchestrator)
    _scheduler.start()

    yield

    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(
    title="Opportunity Discovery Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    from backend.api.websocket import ws_manager
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
