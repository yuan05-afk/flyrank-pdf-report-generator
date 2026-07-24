"""
FlyRank · PDF report generator
Query data -> render PDF -> as a background job. Store the artifact, link to it.

    POST /reports              -> 202 + {report_id, status_url}
    GET  /reports/{id}         -> status (+ download_url when ready)
    GET  /reports/{id}/download-> the PDF file (artifact)
    GET  /health

Stretch: a scheduler thread can generate a report on an interval.
"""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import data
import report_builder

# In-memory report registry (artifacts live on disk in reports/).
_reports: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _build(report_id: str, title: str) -> None:
    with _lock:
        _reports[report_id]["status"] = "running"
    try:
        path = report_builder.build_report(report_id, title)
        with _lock:
            _reports[report_id].update(
                status="succeeded",
                path=str(path),
                size_bytes=path.stat().st_size,
                download_url=f"/reports/{report_id}/download",
            )
        print(f"[report] {report_id} built ({path.stat().st_size} bytes)", flush=True)
    except Exception as exc:
        with _lock:
            _reports[report_id].update(status="failed", error=str(exc))
        print(f"[report] {report_id} FAILED: {exc}", flush=True)


def enqueue_report(title: str) -> str:
    report_id = uuid.uuid4().hex[:12]
    with _lock:
        _reports[report_id] = {
            "id": report_id,
            "title": title,
            "status": "queued",
            "created_at": time.time(),
        }
    threading.Thread(target=_build, args=(report_id, title), daemon=True).start()
    return report_id


class _Scheduler(threading.Thread):
    """Stretch: generate a report on a fixed interval (0 = disabled)."""

    def __init__(self, interval_seconds: float) -> None:
        super().__init__(daemon=True)
        self.interval = interval_seconds
        self._stop = threading.Event()

    def run(self) -> None:
        if self.interval <= 0:
            return
        while not self._stop.wait(self.interval):
            rid = enqueue_report("Scheduled SEO Audit Report")
            print(f"[scheduler] queued {rid}", flush=True)

    def stop(self) -> None:
        self._stop.set()


_scheduler: _Scheduler | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    data.init_db()
    report_builder.REPORTS_DIR.mkdir(exist_ok=True)
    global _scheduler
    _scheduler = _Scheduler(interval_seconds=0)  # set >0 to enable scheduling
    _scheduler.start()
    yield
    if _scheduler:
        _scheduler.stop()


app = FastAPI(
    title="PDF Report Generator",
    version="1.0.0",
    description=(
        "Query data with SQL, render a PDF, and generate it as a **background job**. "
        "POST returns 202 instantly; the artifact is stored on disk and served via a link."
    ),
    lifespan=lifespan,
)


class ReportIn(BaseModel):
    title: str = Field("SEO Audit Report", description="Title printed on the PDF.")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "reports_known": len(_reports)}


@app.post("/reports", status_code=202, tags=["reports"], summary="Request a report (202)")
def create_report(body: ReportIn):
    report_id = enqueue_report(body.title)
    return {
        "report_id": report_id,
        "status": "queued",
        "status_url": f"/reports/{report_id}",
    }


@app.get("/reports/{report_id}", tags=["reports"], summary="Report status")
def report_status(report_id: str):
    with _lock:
        rec = _reports.get(report_id)
    if rec is None:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    return {k: v for k, v in rec.items() if k != "path"}


@app.get("/reports/{report_id}/download", tags=["reports"], summary="Download the PDF artifact")
def download(report_id: str):
    with _lock:
        rec = _reports.get(report_id)
    if rec is None:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    if rec["status"] != "succeeded":
        return JSONResponse(
            status_code=409,
            content={"error": f"Report is '{rec['status']}', not ready to download"},
        )
    path = Path(rec["path"])
    if not path.exists():
        return JSONResponse(status_code=410, content={"error": "Artifact missing"})
    return FileResponse(path, media_type="application/pdf", filename=f"{report_id}.pdf")
