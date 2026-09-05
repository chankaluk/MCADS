"""FastAPI gateway for the MCADS V1.0 service."""

from __future__ import annotations

from base64 import b64decode
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import time
import uuid

from audit_repository import AuditRepository
from core_engine import MultimodalRiskEngine
from dataset_loader import build_record

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:  # Allows utilities and self-tests to be imported without FastAPI.
    FastAPI = None


APP_NAME = "基于深度学习的多模态内容异常检测系统"
APP_VERSION = "V1.0"
MAX_UPLOAD_SIZE = 15 * 1024 * 1024
AUDIT_LOG = Path(os.getenv("MCADS_AUDIT_LOG", "logs/audit.jsonl"))
STATIC_DIR = Path(__file__).parent / "static"
TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
engine = MultimodalRiskEngine(block_threshold=0.50)


def _repository() -> AuditRepository:
    return AuditRepository(AUDIT_LOG)


def audit_content(text_content: str, image_bytes: bytes, trace_id: str | None) -> dict:
    """Validate, score and persist one multimodal audit request."""
    started = time.perf_counter()
    if trace_id is not None and not TRACE_ID_PATTERN.fullmatch(trace_id):
        raise ValueError("trace_id must contain 1-64 letters, digits, '_' or '-'")
    record_id = trace_id or uuid.uuid4().hex
    record = build_record(record_id, text_content, image_bytes)
    result = engine.predict(record.text, record.image_bytes).to_dict()
    payload = {
        "record_id": record.record_id,
        "image_sha256": record.image_sha256,
        "image_type": record.image_type,
        **result,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_audit_log(payload)
    return payload


def _append_audit_log(payload: dict) -> None:
    _repository().append(payload)


def read_audit_history(limit: int = 20) -> list[dict]:
    """Return the newest audit records without exposing raw input content."""
    return _repository().latest(limit)


def read_audit_statistics() -> dict:
    """Return aggregate counts without exposing submitted content."""
    return _repository().statistics()


if FastAPI is not None:
    app = FastAPI(title=APP_NAME, version=APP_VERSION)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def web_console():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    async def health_check() -> dict:
        return {
            "status": "ok",
            "software": APP_NAME,
            "version": APP_VERSION,
            "inference_backend": "hybrid-feature-fusion",
        }

    @app.post("/api/v1/audit/stream")
    async def audit_stream(
        text_content: str = Form(...),
        image_file: UploadFile = File(...),
        trace_id: str | None = Form(default=None),
    ) -> dict:
        image_bytes = await image_file.read(MAX_UPLOAD_SIZE + 1)
        if len(image_bytes) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="image_file exceeds 15MB")
        try:
            result = audit_content(text_content, image_bytes, trace_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "message": "success", "data": result}

    @app.get("/api/v1/audit/history")
    async def audit_history(limit: int = 20) -> dict:
        try:
            records = read_audit_history(limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 200, "message": "success", "data": records}

    @app.get("/api/v1/audit/statistics")
    async def audit_statistics() -> dict:
        return {"code": 200, "message": "success", "data": read_audit_statistics()}
else:
    app = None


def _demo_png() -> bytes:
    """Return a valid 1x1 PNG used by the local smoke test."""
    return b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8A"
        "AQUBAScY42YAAAAASUVORK5CYII="
    )


if __name__ == "__main__":
    report = audit_content("普通会议通知，不含链接。", _demo_png(), "DEMO-001")
    import json
    print(json.dumps(report, ensure_ascii=False, indent=2))
