from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai import ai_enabled, label_groups
from .cluster import pre_cluster, split_group
from .models import ClusterRequest, ClusterResponse, SplitRequest

logging.basicConfig(level=logging.INFO)

STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="ChoreRaid", version="1.0.0")


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    return resp


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "ai": ai_enabled()}


@app.post("/api/cluster", response_model=ClusterResponse)
async def cluster(req: ClusterRequest) -> ClusterResponse:
    groups = pre_cluster(req.files)
    groups, used_ai = await label_groups(groups)
    return ClusterResponse(groups=groups, ai=used_ai, total_files=len(req.files))


@app.post("/api/split", response_model=ClusterResponse)
def split(req: SplitRequest) -> ClusterResponse:
    groups = split_group(req.parent_target, req.files)
    return ClusterResponse(groups=groups, ai=False, total_files=len(req.files))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
