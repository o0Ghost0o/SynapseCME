import pytest

from app.agent.extractor import build_followup, extract
from app.models import EquipmentItem, ExtractionResult


def test_example_observation():
    msg = (
        "Visité el Hospital Aurora en Panamá, vi 3 resonancias magnéticas "
        "y 2 tomógrafos, una RM tiene como 8 años"
    )
    ext = extract(msg)
    assert ext.facility == "Hospital Aurora"
    assert ext.country == "Panamá"
    modalities = sorted(i.modality for i in ext.items)
    assert modalities == ["CT", "MR"]
    mr = next(i for i in ext.items if i.modality == "MR")
    ct = next(i for i in ext.items if i.modality == "CT")
    assert mr.quantity == 3
    assert mr.age_years == 8
    assert ct.quantity == 2
    assert ext.extractor == "rule"


def test_spanish_number_words():
    ext = extract("En el Hospital San José vi dos resonancias y un tomógrafo")
    qty = {i.modality: i.quantity for i in ext.items}
    assert qty.get("MR") == 2
    assert qty.get("CT") == 1


def test_modality_synonyms():
    assert {i.modality for i in extract("vi una TC y una radiografía").items} == {"CT", "XR"}
    assert {i.modality for i in extract("hay ultrasonidos en sala 3").items} == {"UL"}
    assert {i.modality for i in extract("instalamos una RM nueva").items} == {"MR"}


def test_no_facility_no_items():
    ext = extract("hoy llovió mucho en la ciudad")
    assert ext.facility is None
    assert ext.items == []


def test_city_pattern():
    ext = extract("Visité el Hospital Central en Colón, Panamá, vi 1 resonancia")
    assert ext.city == "Colón"
    assert ext.country == "Panamá"


def test_city_from_facility_name():
    msg = (
        "En el Hospital General de Valencia hay 2 resonancias "
        "Siemens MAGNETOM Vida de 9 años, modalidad confirmada"
    )
    ext = extract(msg)
    assert ext.facility == "Hospital General de Valencia"
    assert ext.city == "Valencia"
    assert ext.country == "España"
    mr = next(i for i in ext.items if i.modality == "MR")
    assert mr.quantity == 2
    assert mr.age_years == 9
    assert mr.manufacturer == "Siemens"


def test_city_from_gazetteer():
    ext = extract("Hice mantenimiento en Bogotá, vi un tomógrafo Philips")
    assert ext.city == "Bogotá"
    assert ext.country == "Colombia"


def test_manufacturer_detected():
    ext = extract("El Hospital Norte tiene una resonancia Siemens de 5 años")
    assert ext.items[0].manufacturer == "Siemens"
    assert ext.items[0].age_years == 5


def test_followup_when_manufacturer_missing():
    ext = ExtractionResult(
        facility="Hospital Aurora",
        country="Panamá",
        items=[EquipmentItem(modality="MR", quantity=3)],
    )
    question = build_followup(ext)
    assert question is not None
    assert "fabricante" in question.lower()


def test_no_followup_when_manufacturer_known():
    ext = ExtractionResult(
        facility="Hospital Aurora",
        country="Panamá",
        items=[EquipmentItem(modality="MR", manufacturer="GE", quantity=1)],
    )
    assert build_followup(ext) is None


# --- Parámetros técnicos (fallback determinista) ---------------------------


def _params_by_name(ext, modality):
    item = next(i for i in ext.items if i.modality == modality)
    return {p.name: p for p in item.parameters}


def test_parameter_helium_low_and_pressure_ok():
    ext = extract(
        "En el Hospital Aurora en Ciudad de Panamá, Panamá, la resonancia "
        "magnética Siemens tiene el nivel de helio bajo al 45% (rango nominal "
        "60-100%) y la presión de criógeno normal"
    )
    params = _params_by_name(ext, "MR")
    helio = params["nivel de helio"]
    assert helio.value == 45
    assert helio.unit == "%"
    assert helio.status == "warning"
    presion = params["presión"]
    assert presion.value is None
    assert presion.status == "ok"


def test_parameter_tube_cuts_scaled_and_anode_warning():
    ext = extract(
        "El tomógrafo GE del Hospital Aurora en Panamá tiene el tubo con "
        "1.2 millones de cortes, el calentamiento del ánodo está alto"
    )
    params = _params_by_name(ext, "CT")
    cortes = params["cortes de tubo"]
    assert cortes.value == 1200000
    assert cortes.unit == "cortes"
    assert cortes.status == "warning"
    anodo = params["calentamiento del ánodo"]
    assert anodo.value is None
    assert anodo.status == "warning"


def test_parameter_current_out_of_range_critical():
    ext = extract(
        "En el Hospital Aurora en Panamá la fluoroscopia Siemens tiene la "
        "corriente del tubo fuera de rango a 15 mA (nominal 5-10 mA)"
    )
    corriente = _params_by_name(ext, "RF")["corriente"]
    assert corriente.value == 15
    assert corriente.unit == "mA"
    assert corriente.status == "critical"


def test_parameter_nominal_values_are_ok():
    ext = extract(
        "En el Centro Médico Bahía en San José, Costa Rica, la resonancia "
        "Siemens tiene el nivel de helio nominal al 98% y la presión de "
        "criógeno correcta"
    )
    params = _params_by_name(ext, "MR")
    assert params["nivel de helio"].value == 98
    assert params["nivel de helio"].status == "ok"
    assert params["presión"].status == "ok"


def test_no_parameters_when_no_magnitudes():
    ext = extract("Visité el Hospital Aurora en Panamá, vi 3 resonancias magnéticas")
    assert all(i.parameters == [] for i in ext.items)
