"""Duplicate-matching logic (engine._pick_equipment) — pure, no DB."""

from app.graph.engine import _pick_equipment

GE = {"id": "eq-1", "manufacturer": "GE", "model": None, "state": "Confirmado"}
SIEMENS = {"id": "eq-2", "manufacturer": "Siemens", "model": None, "state": "Estimado"}
UNKNOWN = {"id": "eq-3", "manufacturer": None, "model": None, "state": "Estimado"}
LIGHTSPEED = {"id": "eq-4", "manufacturer": "GE", "model": "Lightspeed", "state": "Estimado"}


class TestPickEquipment:
    def test_no_candidates_creates_new(self):
        assert _pick_equipment([], "Siemens", None) is None

    def test_exact_manufacturer_match(self):
        assert _pick_equipment([GE, SIEMENS], "siemens", None)["id"] == "eq-2"

    def test_unknown_manufacturer_gets_upgraded(self):
        assert _pick_equipment([UNKNOWN], "Siemens", None)["id"] == "eq-3"

    def test_conflicting_known_manufacturer_is_a_new_unit(self):
        # Siemens report where only GE is known must NOT overwrite the GE node.
        assert _pick_equipment([GE], "Siemens", None) is None
        assert _pick_equipment([GE, LIGHTSPEED], "Philips", None) is None

    def test_exact_model_match(self):
        assert _pick_equipment([GE, LIGHTSPEED], None, "lightspeed")["id"] == "eq-4"

    def test_unknown_model_gets_upgraded(self):
        no_model = {"id": "eq-5", "manufacturer": "GE", "model": None, "state": "Estimado"}
        assert _pick_equipment([no_model], None, "Lightspeed")["id"] == "eq-5"

    def test_conflicting_known_model_is_a_new_unit(self):
        assert _pick_equipment([LIGHTSPEED], None, "Aquilion") is None

    def test_no_identification_reuses_first_candidate(self):
        assert _pick_equipment([GE, SIEMENS], None, None)["id"] == "eq-1"
