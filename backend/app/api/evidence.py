"""Evidence storage and serving endpoints."""

from __future__ import annotations

import base64
import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger("synapse.evidence")
router = APIRouter(tags=["evidence"])

EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", "volumes/evidence"))


def _ensure_dir() -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    return EVIDENCE_DIR


def save_evidence_base64(raw: str) -> str:
    """Save a base64 or data URL image to the evidence directory and return its URL."""
    if not raw or not raw.strip():
        return ""
    text = raw.strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if "/api/evidence/" in text:
        clean_name = Path(text).name
        if clean_name.startswith("ev_"):
            return f"/api/evidence/{clean_name}"
        return text
    if text.startswith("ev_") and "." in text:
        return f"/api/evidence/{text}"

    # Extract base64 payload from data URL if present
    match = re.match(r"^data:image\/([a-zA-Z0-9]+);base64,(.+)$", text, re.DOTALL)
    if match:
        ext = match.group(1).lower()
        if ext == "jpeg":
            ext = "jpg"
        b64_data = match.group(2)
    else:
        ext = "jpg"
        b64_data = text

    try:
        binary_data = base64.b64decode(b64_data)
    except Exception as exc:
        logger.warning("No se pudo decodificar la imagen de evidencia: %s", exc)
        return ""

    out_dir = _ensure_dir()
    filename = f"ev_{uuid.uuid4().hex[:12]}.{ext}"
    target_path = out_dir / filename
    try:
        target_path.write_bytes(binary_data)
        logger.info("Evidencia guardada: %s (%d bytes)", filename, len(binary_data))
        return f"/api/evidence/{filename}"
    except Exception as exc:
        logger.exception("Error al guardar archivo de evidencia: %s", exc)
        return ""


@router.get("/api/evidence/{filename:path}")
async def get_evidence(filename: str) -> FileResponse:
    """Serve an uploaded evidence photo."""
    # Prevent path traversal and safely extract the filename
    safe_name = Path(filename).name
    if not safe_name or safe_name.startswith(".") or ".." in filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")

    target_path = _ensure_dir() / safe_name
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")

    ext = target_path.suffix.lower()
    media_type = (
        "image/jpeg"
        if ext in (".jpg", ".jpeg")
        else "image/png"
        if ext == ".png"
        else "application/octet-stream"
    )
    return FileResponse(
        str(target_path),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
