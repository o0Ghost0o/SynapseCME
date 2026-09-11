"""Tests for evidence saving, normalization, and serving endpoints."""

from __future__ import annotations

import base64
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api import evidence
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_evidence_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "EVIDENCE_DIR", tmp_path)
    return tmp_path


def test_save_evidence_empty():
    assert evidence.save_evidence_base64("") == ""
    assert evidence.save_evidence_base64("   ") == ""


def test_save_evidence_urls():
    assert evidence.save_evidence_base64("https://example.com/photo.jpg") == "https://example.com/photo.jpg"
    assert evidence.save_evidence_base64("http://example.com/photo.png") == "http://example.com/photo.png"


def test_save_evidence_existing_api_paths():
    assert evidence.save_evidence_base64("/api/evidence/ev_abcdef123456.jpg") == "/api/evidence/ev_abcdef123456.jpg"
    # Duplicate path segment
    assert evidence.save_evidence_base64("/api/evidence//api/evidence/ev_abcdef123456.jpg") == "/api/evidence/ev_abcdef123456.jpg"


def test_save_evidence_base64_data_url(temp_evidence_dir):
    sample_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b64_str = base64.b64encode(sample_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{b64_str}"

    result = evidence.save_evidence_base64(data_url)
    assert result.startswith("/api/evidence/ev_")
    assert result.endswith(".png")

    # Verify file was written
    filename = Path(result).name
    saved_file = temp_evidence_dir / filename
    assert saved_file.is_file()
    assert saved_file.read_bytes() == sample_bytes


def test_save_evidence_raw_base64(temp_evidence_dir):
    sample_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    b64_str = base64.b64encode(sample_bytes).decode("ascii")

    result = evidence.save_evidence_base64(b64_str)
    assert result.startswith("/api/evidence/ev_")
    assert result.endswith(".jpg")

    filename = Path(result).name
    saved_file = temp_evidence_dir / filename
    assert saved_file.is_file()
    assert saved_file.read_bytes() == sample_bytes


def test_get_evidence_success(client, temp_evidence_dir):
    test_file = temp_evidence_dir / "ev_testphoto12.jpg"
    test_file.write_bytes(b"\xff\xd8\xff\xe0JPEG_DATA")

    resp = client.get("/api/evidence/ev_testphoto12.jpg")
    assert resp.status_code == 200
    assert resp.content == b"\xff\xd8\xff\xe0JPEG_DATA"
    assert resp.headers["content-type"] == "image/jpeg"
    assert "public, max-age=86400" in resp.headers["cache-control"]


def test_get_evidence_nested_or_duplicate_path(client, temp_evidence_dir):
    test_file = temp_evidence_dir / "ev_testphoto12.jpg"
    test_file.write_bytes(b"\xff\xd8\xff\xe0JPEG_DATA")

    # The client requested /api/evidence/api/evidence/ev_testphoto12.jpg
    resp = client.get("/api/evidence/api/evidence/ev_testphoto12.jpg")
    assert resp.status_code == 200
    assert resp.content == b"\xff\xd8\xff\xe0JPEG_DATA"


def test_get_evidence_not_found(client, temp_evidence_dir):
    resp = client.get("/api/evidence/ev_nonexistent.jpg")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Evidencia no encontrada"


def test_get_evidence_path_traversal_rejected(client, temp_evidence_dir):
    resp = client.get("/api/evidence/../secret.txt")
    assert resp.status_code in (400, 404)

    resp = client.get("/api/evidence/.hidden_file")
    assert resp.status_code == 400
