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
