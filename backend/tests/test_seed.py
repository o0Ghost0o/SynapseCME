"""Seed dataset validation — pure data checks, no live DB required."""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
# Repo checkout: tests live in backend/tests (repo root = parents[2]).
# Container image (Dockerfile.test): everything is copied under /app.
for root in {_HERE.parents[2], _HERE.parents[1]}:
    for sub in (root, root / "backend"):
        if (sub / "data").is_dir() or (sub / "app").is_dir():
            sp = str(sub)
            if sp not in sys.path:
                sys.path.insert(0, sp)

from data.synthetic.seed import (  # noqa: E402
    CONTRIBUTORS,
    DATASET,
    EXPECTED_COUNTRIES,
    EXPECTED_FACILITIES,
    load_dataset,
    validate_dataset,
)


def test_dataset_is_valid():
    errors = validate_dataset()
    assert errors == [], f"errores de validación: {errors}"


def test_dataset_shape():
    records = load_dataset()
    assert len(records) == len(DATASET) >= 35
    assert {r.contributor for r in records} == set(CONTRIBUTORS)
    assert all(r.client_type == "field_app" for r in records)


def test_expected_facilities_and_countries():
    records = load_dataset()
    facilities = set()
    countries = set()
    from app.agent.extractor import extract

    for r in records:
        ext = extract(r.message)
        if ext.facility:
            facilities.add(ext.facility)
        if ext.country:
            countries.add(ext.country)
    assert facilities == EXPECTED_FACILITIES
    assert countries == EXPECTED_COUNTRIES


def test_consensus_coverage_in_data():
    """Dataset must contain cross-contributor duplicates (Confirmado path)
    and same-contributor repeats (Reportado path)."""
    from app.agent.extractor import extract

    facility_contributors: dict[str, set[str]] = {}
    facility_same_contributor_counts: dict[tuple[str, str], int] = {}
    for r in load_dataset():
        ext = extract(r.message)
        if not ext.facility:
            continue
        facility_contributors.setdefault(ext.facility, set()).add(r.contributor)
        key = (ext.facility, r.contributor)
        facility_same_contributor_counts[key] = (
            facility_same_contributor_counts.get(key, 0) + 1
        )

    multi = {f for f, cs in facility_contributors.items() if len(cs) >= 2}
    assert "Hospital Aurora" in multi
    assert len(multi) >= 3
    assert any(n >= 2 for n in facility_same_contributor_counts.values())


def test_no_real_institution_names():
    from app.agent.extractor import extract

    for r in load_dataset():
        ext = extract(r.message)
        assert ext.facility not in {"La Paz", "Mayo Clinic", "Cleveland Clinic"}
        blob = r.message.lower()
        for blocked in ("mayo", "hopkins", "karolinska", "stanford", "harvard"):
            assert blocked not in blob, f"nombre real en: {r.message!r}"
