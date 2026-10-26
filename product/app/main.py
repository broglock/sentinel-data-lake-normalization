"""LevelBlue Lake Hunt: web UI, REST API and MCP server in one process.

Run locally (demo mode, no Azure):   uvicorn app.main:app --port 8080
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import APP_DIR, settings
from app.core import Core
from app.routers import api, mcp
from app.store import Store

log = logging.getLogger("lakehunt")


def make_provider():
    if settings.mode == "live":
        missing = settings.live_ready
        if missing:
            raise RuntimeError(f"Live mode needs: {', '.join(missing)}")
        from app.providers.azure import AzureProvider
        return AzureProvider()
    from app.providers.demo import DemoProvider
    return DemoProvider()


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = Store(settings.data_dir / f"lakehunt-{settings.mode}.db")
    core = Core(store, make_provider())
    try:
        core.bootstrap()
    except Exception as e:  # noqa: BLE001
        log.exception("bootstrap failed: %s", e)
    app.state.core = core
    yield


app = FastAPI(title=settings.product_name, version=settings.version, lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json",
              description="Normalize hundreds of log sources in the Microsoft Sentinel data lake into one hunt "
                          "index with ASIM field names. Onboard sources, decide field mappings, validate, hunt.")
app.include_router(api.router)
app.include_router(mcp.router)


@app.get("/healthz", include_in_schema=False)
def health():
    return JSONResponse({"ok": True, "mode": settings.mode, "version": settings.version})


app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    return FileResponse(APP_DIR / "static" / "index.html", headers={"Cache-Control": "no-cache"})
