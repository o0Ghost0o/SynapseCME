"""Endpoints de equipos: detalle con parámetros y lista plana filtrada.

Sin Neo4j real: engine.driver/engine.get_equipment_detail/engine.list_equipments
se mockean; la auth real se pasa por dependency override (patrón de test_auth).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user
from app.graph import engine
from app.main import app


def make_user(username="visor.ana", role="viewer"):
    return {
        "id": 2,
        "username": username,
        "full_name": "Ana Visor",
        "role": role,
        "disabled": False,
        "created_at": "2026-01-01T00:00:00Z",
    }


def client_as(role: str = "viewer") -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: make_user(role=role)
    return TestClient(app)


EQUIPMENT_FIXTURE = {
    "equipment": {
        "id": "eq-1",
        "modality": "MR",
        "manufacturer": "Siemens",
        "model": "MAGNETOM Vida",
        "quantity": 1,
        "age_years": 6,
        "state": "Confirmado",
        "facility_id": "fac-1",
        "facility_name": "Hospital Aurora",
        "city": "Ciudad de Panamá",
        "country": "Panamá",
    },
    "observations": [
        {
            "id": "obs-1",
            "contributor": "marina.solis",
            "text": "nivel de helio bajo al 45%",
            "confidence": 0.8,
            "created_at": "2026-09-01T10:00:00Z",
        }
    ],
    "parameters": [
        {
            "id": "par-2",
            "name": "nivel de helio",
            "value": 98,
            "unit": "%",
            "status": "ok",
            "source_observation_id": "obs-2",
            "created_at": "2026-09-09T10:00:00Z",
        }
    ],
    "parameter_history": [
        {
            "id": "par-2",
            "name": "nivel de helio",
            "value": 98,
            "unit": "%",
            "status": "ok",
            "source_observation_id": "obs-2",
            "created_at": "2026-09-09T10:00:00Z",
        },
        {
            "id": "par-1",
            "name": "nivel de helio",
            "value": 45,
            "unit": "%",
            "status": "warning",
            "source_observation_id": "obs-1",
            "created_at": "2026-09-01T10:00:00Z",
        },
    ],
}


@pytest.fixture(autouse=True)
def _clean_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


class TestEquipmentDetail:
    def test_detail_ok(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())

        async def fake_detail(eid):
            return EQUIPMENT_FIXTURE if eid == "eq-1" else None

        monkeypatch.setattr(engine, "get_equipment_detail", fake_detail)
        r = client_as().get("/api/equipment/eq-1")
        assert r.status_code == 200
        body = r.json()
        assert body["equipment"]["manufacturer"] == "Siemens"
        assert body["observations"][0]["id"] == "obs-1"
        # parameters = último valor por nombre; parameter_history = completo
        assert body["parameters"][0]["value"] == 98
        assert len(body["parameter_history"]) == 2
        assert body["parameter_history"][1]["status"] == "warning"

    def test_detail_not_found(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())

        async def fake_detail(eid):
            return None

        monkeypatch.setattr(engine, "get_equipment_detail", fake_detail)
        r = client_as().get("/api/equipment/eq-nope")
        assert r.status_code == 404
        assert "Equipo no encontrado" in r.json()["detail"]

    def test_detail_graph_down_503(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: None)
        r = client_as().get("/api/equipment/eq-1")
        assert r.status_code == 503

    def test_detail_requires_auth(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())
        r = TestClient(app).get("/api/equipment/eq-1")
        assert r.status_code == 401


class TestEquipmentList:
    def test_list_defaults_and_shape(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())
        captured = {}

        async def fake_list(**kwargs):
            captured.update(kwargs)
            return {"total": 1, "items": [EQUIPMENT_FIXTURE["equipment"] | {"has_issue": True}]}

        monkeypatch.setattr(engine, "list_equipments", fake_list)
        r = client_as().get("/api/equipments")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["limit"] == 100
        assert body["offset"] == 0
        assert body["items"][0]["id"] == "eq-1"
        assert body["items"][0]["has_issue"] is True
        assert captured["modality"] is None
        assert captured["has_issue"] is False

    def test_list_forwards_filters(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())
        captured = {}

        async def fake_list(**kwargs):
            captured.update(kwargs)
            return {"total": 0, "items": []}

        monkeypatch.setattr(engine, "list_equipments", fake_list)
        r = client_as().get(
            "/api/equipments",
            params={
                "modality": "MR",
                "manufacturer": "siemens",
                "state": "Confirmado",
                "country": "Panamá",
                "facility": "fac-1",
                "q": "MAGNETOM",
                "has_issue": "true",
                "limit": "10",
                "offset": "20",
            },
        )
        assert r.status_code == 200
        assert captured["modality"] == "MR"
        assert captured["manufacturer"] == "siemens"
        assert captured["state"] == "Confirmado"
        assert captured["country"] == "Panamá"
        assert captured["facility"] == "fac-1"
        assert captured["q"] == "MAGNETOM"
        assert captured["has_issue"] is True
        assert captured["limit"] == 10
        assert captured["offset"] == 20

    def test_list_graph_down_503(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: None)
        r = client_as().get("/api/equipments")
        assert r.status_code == 503

    def test_list_requires_auth(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())
        assert TestClient(app).get("/api/equipments").status_code == 401

    def test_list_viewer_role_allowed(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())

        async def fake_list(**kwargs):
            return {"total": 0, "items": []}

        monkeypatch.setattr(engine, "list_equipments", fake_list)
        assert client_as("viewer").get("/api/equipments").status_code == 200


class TestEquipmentChat:
    """Mini-chat de revisión anclado al equipo (SSE, contrato como /api/chat)."""

    CTX = {
        "id": "eq-1",
        "modality": "MR",
        "manufacturer": None,
        "model": None,
        "age_years": None,
        "state": "Desconocido",
        "facility_id": "fac-1",
        "facility_name": "Clínica Puerto Verde",
        "city": "Colón",
        "country": "Panamá",
    }

    def test_chat_not_found(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())

        async def fake_ctx(eid):
            return None

        monkeypatch.setattr(engine, "get_equipment_context", fake_ctx)
        r = client_as("capturer").post(
            "/api/equipment/eq-nope/chat", json={"message": "El fabricante es Philips"}
        )
        assert r.status_code == 404

    def test_chat_streams_sse(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())

        async def fake_ctx(eid):
            return self.CTX

        monkeypatch.setattr(engine, "get_equipment_context", fake_ctx)

        async def fake_stream(message, equipment_id, user, client_type=None):
            assert message == "El fabricante es Philips"
            assert equipment_id == "eq-1"
            yield 'data: {"type": "token", "text": "Listo"}\n\n'
            yield 'data: {"type": "done", "transaction_id": 5}\n\n'

        monkeypatch.setattr("app.api.equipment.service.handle_equipment_chat", fake_stream)
        r = client_as("capturer").post(
            "/api/equipment/eq-1/chat", json={"message": "El fabricante es Philips"}
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert '"type": "done"' in r.text

    def test_chat_graph_down_503(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: None)
        r = client_as("capturer").post("/api/equipment/eq-1/chat", json={"message": "x"})
        assert r.status_code == 503

    def test_chat_viewer_forbidden(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())
        r = client_as("viewer").post("/api/equipment/eq-1/chat", json={"message": "x"})
        assert r.status_code == 403

    def test_chat_requires_auth(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())
        r = TestClient(app).post("/api/equipment/eq-1/chat", json={"message": "x"})
        assert r.status_code == 401


class TestPatchEquipment:
    def test_patch_equipment_success(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())

        async def fake_patch(eid, data, **kwargs):
            return {
                "equipment": {
                    "id": eid,
                    "modality": "CT",
                    "manufacturer": data.manufacturer or "GE",
                    "model": data.model or "LightSpeed",
                    "age_years": data.age_years if data.age_years is not None else 4.0,
                    "quantity": data.quantity or 1,
                    "state": "Estimado",
                    "facility_name": "Hospital Santo Tomas",
                    "city": "Panama",
                    "country": "Panama",
                },
                "parameters": [
                    {
                        "id": "par-1",
                        "source_observation_id": "obs-1",
                        "name": "voltaje",
                        "value": 120.0,
                        "unit": "V",
                        "status": "ok",
                    }
                ],
                "observations": [],
            }

        monkeypatch.setattr(engine, "patch_equipment", fake_patch)
        r = client_as("capturer").patch(
            "/api/equipment/eq-1",
            json={
                "manufacturer": "GE",
                "model": "Optima",
                "parameters": [
                    {"name": "voltaje", "value": 120.0, "unit": "V", "status": "ok"}
                ],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["equipment"]["id"] == "eq-1"
        assert data["equipment"]["model"] == "Optima"

    def test_patch_equipment_not_found(self, monkeypatch):
        monkeypatch.setattr(engine, "driver", lambda: object())

        async def fake_patch(eid, data, **kwargs):
            return None

        monkeypatch.setattr(engine, "patch_equipment", fake_patch)
        r = client_as("capturer").patch(
            "/api/equipment/eq-nonexistent",
            json={"model": "Test"},
        )
        assert r.status_code == 404
