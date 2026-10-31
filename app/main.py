"""ChoreRaid HTTP API: plans folder clean-ups; the browser executes the moves."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai import ai_enabled, label_groups
from .cache import PlanCache
from .cluster import pre_cluster, split_group
from .models import ClusterRequest, ClusterResponse, SplitRequest

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_MAX_AGE = 3600  # seconds browsers may cache JS/CSS
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

app = FastAPI(title="ChoreRaid", version="1.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)  # file lists compress ~10x

plan_cache = PlanCache(max_entries=128)


@app.middleware("http")
async def headers_middleware(request: Request, call_next) -> Response:
    """Add security headers everywhere and long-lived caching for static assets."""
    resp = await call_next(request)
    resp.headers.update(SECURITY_HEADERS)
    if request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = f"public, max-age={STATIC_MAX_AGE}"
    elif request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True, "ai": ai_enabled()}


@app.post("/api/cluster", response_model=ClusterResponse)
async def cluster(req: ClusterRequest) -> ClusterResponse:
    """Group files into bosses. Identical folders are served from an in-memory cache."""
    key = PlanCache.key_for(req.files)
    cached = plan_cache.get(key)
    if cached is not None:
        return cached
    groups, used_ai = await label_groups(pre_cluster(req.files))
    result = ClusterResponse(groups=groups, ai=used_ai, total_files=len(req.files))
    if used_ai:  # only cache real AI plans; rule plans are already instant
        plan_cache.put(key, result)
    return result


@app.post("/api/split", response_model=ClusterResponse)
def split(req: SplitRequest) -> ClusterResponse:
    groups = split_group(req.parent_target, req.files)
    return ClusterResponse(groups=groups, ai=False, total_files=len(req.files))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
