"""Synthetic seed data for SynapseCME — strictly fictional institutions.

Every hospital, clinic and person in this file is invented. The loader routes
each observation through the app's real pipeline (rule extractor ->
graph engine ingest -> consensus states -> transaction_log + WS events),
so seeding exercises exactly the code path used in production.

Usage (from repo root, with the backend venv active):

    python data/synthetic/seed.py            # append to current graph
    python data/synthetic/seed.py --wipe     # reset graph + logs first
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# Make the backend package importable regardless of the caller's CWD.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
for _p in (str(_BACKEND), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app import db  # noqa: E402
from app.agent import extractor as rule_extractor  # noqa: E402
from app.auth import service as auth_service  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.graph import engine  # noqa: E402

logger = logging.getLogger("synapse.seed")

CONTRIBUTOR_PASSWORD = "synapse-dev"  # documented dev password for seed users


def contributor_username(full_name: str) -> str:
    """Deterministic username: 'Marina Solís' -> 'marina.solis'."""
    parts = full_name.lower().replace("í", "i").replace("é", "e").replace("á", "a") \
        .replace("ó", "o").replace("ú", "u").split()
    return ".".join(parts)

CONTRIBUTORS = ["Marina Solís", "Jorge Iriarte", "Camila Duarte"]
CLIENT_TYPE = "field_app"

# Real institution names that must never appear in the seed data.
REAL_NAMES_BLOCKLIST = [
    "mayo clinic", "john hopkins", "cleveland clinic", "mount sinai",
    "mass general", "md anderson", "karolinska", "charité", "pitié",
    "hospital general de", "la paz", "clínica las condes", "hospital israelita",
    "stanford", "harvard", "ucla", "nyu langone", "bambino gesù",
]


@dataclass(frozen=True)
class SeedObservation:
    message: str
    contributor: str
    client_type: str = CLIENT_TYPE


# ---------------------------------------------------------------------------
# Dataset: 4 países de LATAM (mayoría Panamá), 8 fictional facilities,
# 44 observations.
# Deliberate duplicates across contributors drive consensus promotion
# (Estimado -> Reportado -> Confirmado) and conflicting manufacturer/age
# reports on the same unit. The last four observations carry technical
# parameters (good and bad) to exercise the Parameter pipeline.
# ---------------------------------------------------------------------------

DATASET: list[SeedObservation] = [
    # --- Hospital Aurora (Ciudad de Panamá, Panamá) — 8 obs -----------------
    SeedObservation(
        "Visité el Hospital Aurora en Ciudad de Panamá, Panamá, vi 3 resonancias "
        "magnéticas y 2 tomógrafos, una RM tiene como 8 años",
        "Marina Solís",
    ),
    SeedObservation(
        "Confirmo en el Hospital Aurora en Ciudad de Panamá, Panamá: las 3 "
        "resonancias magnéticas son Siemens y una tiene unos 10 años",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "En el Hospital Aurora en Panamá hay 2 tomógrafos GE y una radiografía",
        "Camila Duarte",
    ),
    SeedObservation(
        "Vi la radiografía del Hospital Aurora en Panamá funcionando bien",
        "Marina Solís",
    ),
    SeedObservation(
        "Hay un ultrasonido en el Hospital Aurora en Ciudad de Panamá",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "El Hospital Aurora en Panamá tiene mamografía",
        "Camila Duarte",
    ),
    SeedObservation(
        "También vi fluoroscopia en el Hospital Aurora en Panamá",
        "Marina Solís",
    ),
    SeedObservation(
        "El tomógrafo del Hospital Aurora en Panamá ya tiene como 12 años",
        "Jorge Iriarte",
    ),
    # --- Clínica del Norte (Bogotá, Colombia) — 6 obs -----------------------
    SeedObservation(
        "Visité la Clínica del Norte en Bogotá, Colombia, vi 2 resonancias "
        "magnéticas Philips de unos 5 años",
        "Marina Solís",
    ),
    SeedObservation(
        "En la Clínica del Norte en Bogotá, Colombia, confirmo 2 resonancias "
        "magnéticas Philips",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "La Clínica del Norte en Bogotá, Colombia, tiene 4 tomógrafos",
        "Camila Duarte",
    ),
    SeedObservation(
        "Vi 3 tomógrafos en la Clínica del Norte en Bogotá, Colombia, todos operativos",
        "Camila Duarte",
    ),
    SeedObservation(
        "Hay un ultrasonido y una radiografía en la Clínica del Norte en Bogotá, Colombia",
        "Marina Solís",
    ),
    SeedObservation(
        "La Clínica del Norte en Bogotá, Colombia, instaló una mamografía nueva",
        "Jorge Iriarte",
    ),
    # --- Clínica Puerto Verde (Colón, Panamá) — 4 obs -----------------------
    SeedObservation(
        "Visité la Clínica Puerto Verde en Colón, Panamá, vi 1 resonancia magnética",
        "Marina Solís",
    ),
    SeedObservation(
        "En la Clínica Puerto Verde en Colón, Panamá, la resonancia es Canon",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "La Clínica Puerto Verde en Colón, Panamá, tiene 2 ultrasonidos",
        "Camila Duarte",
    ),
    SeedObservation(
        "Vi una radiografía en la Clínica Puerto Verde en Colón, Panamá",
        "Marina Solís",
    ),
    # --- Hospital del Faro (Cartagena, Colombia) — 4 obs --------------------
    SeedObservation(
        "Visité el Hospital del Faro en Cartagena, Colombia, vi 2 tomógrafos",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "El Hospital del Faro en Cartagena, Colombia, tiene 1 resonancia magnética GE",
        "Camila Duarte",
    ),
    SeedObservation(
        "Confirmo los 2 tomógrafos del Hospital del Faro en Cartagena, Colombia, son Philips",
        "Marina Solís",
    ),
    SeedObservation(
        "Hay 3 ultrasonidos en el Hospital del Faro en Cartagena, Colombia",
        "Jorge Iriarte",
    ),
    # --- Centro Médico Bahía (San José, Costa Rica) — 5 obs -----------------
    SeedObservation(
        "Visité el Centro Médico Bahía en San José, Costa Rica, vi 2 resonancias "
        "magnéticas y 1 tomógrafo",
        "Camila Duarte",
    ),
    SeedObservation(
        "En el Centro Médico Bahía en San José, Costa Rica, las resonancias son "
        "Siemens y el tomógrafo es GE",
        "Marina Solís",
    ),
    SeedObservation(
        "El Centro Médico Bahía en San José, Costa Rica, tiene 2 radiografías",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "Vi una mamografía en el Centro Médico Bahía en San José, Costa Rica",
        "Camila Duarte",
    ),
    SeedObservation(
        "Hay un ultrasonido en el Centro Médico Bahía en San José, Costa Rica",
        "Marina Solís",
    ),
    # --- Hospital Istmo (David, Panamá) — 5 obs ------------------------------
    SeedObservation(
        "Visité el Hospital Istmo en David, Panamá, vi 2 resonancias "
        "magnéticas y 1 mamografía",
        "Marina Solís",
    ),
    SeedObservation(
        "En el Hospital Istmo en David, Panamá, las 2 resonancias magnéticas "
        "son GE de unos 6 años",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "El Hospital Istmo en David, Panamá, tiene 3 tomógrafos",
        "Camila Duarte",
    ),
    SeedObservation(
        "Vi 2 tomógrafos del Hospital Istmo en David, Panamá, operativos",
        "Marina Solís",
    ),
    SeedObservation(
        "Hay 2 ultrasonidos en el Hospital Istmo en David, Panamá",
        "Jorge Iriarte",
    ),
    # --- Clínica Monte Azul (Penonomé, Panamá) — 4 obs -----------------------
    SeedObservation(
        "Visité la Clínica Monte Azul en Penonomé, Panamá, vi 1 resonancia "
        "magnética y 2 radiografías",
        "Camila Duarte",
    ),
    SeedObservation(
        "La Clínica Monte Azul en Penonomé, Panamá, tiene 1 tomógrafo GE "
        "de unos 4 años",
        "Marina Solís",
    ),
    SeedObservation(
        "Confirmo la resonancia de la Clínica Monte Azul en Penonomé, Panamá, "
        "es Siemens",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "Hay 2 mamografías en la Clínica Monte Azul en Penonomé, Panamá",
        "Camila Duarte",
    ),
    # --- Centro Médico Andino (Lima, Perú) — 4 obs ---------------------------
    SeedObservation(
        "Visité el Centro Médico Andino en Lima, Perú, vi 3 tomógrafos Siemens",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "El Centro Médico Andino en Lima, Perú, tiene 2 resonancias magnéticas "
        "Philips de unos 7 años",
        "Camila Duarte",
    ),
    SeedObservation(
        "Confirmo los 3 tomógrafos Siemens del Centro Médico Andino en Lima, Perú",
        "Marina Solís",
    ),
    SeedObservation(
        "Vi 4 ultrasonidos en el Centro Médico Andino en Lima, Perú",
        "Jorge Iriarte",
    ),
    # --- Observaciones con parámetros técnicos (buenos y malos) -------------
    SeedObservation(
        "En el Hospital Aurora en Ciudad de Panamá, Panamá, la resonancia "
        "magnética Siemens tiene el nivel de helio bajo al 45% (rango nominal "
        "60-100%) y la presión de criógeno normal",
        "Marina Solís",
    ),
    SeedObservation(
        "El tomógrafo GE del Hospital Aurora en Panamá tiene el tubo con "
        "1.2 millones de cortes, el calentamiento del ánodo está alto",
        "Jorge Iriarte",
    ),
    SeedObservation(
        "En el Hospital Aurora en Panamá la fluoroscopia Siemens tiene la "
        "corriente del tubo fuera de rango a 15 mA (nominal 5-10 mA)",
        "Camila Duarte",
    ),
    SeedObservation(
        "En el Centro Médico Bahía en San José, Costa Rica, la resonancia "
        "Siemens tiene el nivel de helio nominal al 98% y la presión de "
        "criógeno correcta",
        "Marina Solís",
    ),
]

EXPECTED_FACILITIES = {
    "Hospital Aurora",
    "Clínica del Norte",
    "Clínica Puerto Verde",
    "Hospital del Faro",
    "Centro Médico Bahía",
    "Hospital Istmo",
    "Clínica Monte Azul",
    "Centro Médico Andino",
}

EXPECTED_COUNTRIES = {"Panamá", "Colombia", "Costa Rica", "Perú"}


def load_dataset() -> list[SeedObservation]:
    return list(DATASET)


def validate_dataset(records: list[SeedObservation] | None = None) -> list[str]:
    """Structural validation as pure data (no DB required). Returns errors."""
    records = records if records is not None else load_dataset()
    errors: list[str] = []

    contributors = {r.contributor for r in records}
    if contributors != set(CONTRIBUTORS):
        errors.append(f"contributors {contributors} != {set(CONTRIBUTORS)}")
    if not (35 <= len(records) <= 60):
        errors.append(f"observation count {len(records)} fuera de rango 35..60")

    facilities: set[str] = set()
    countries: set[str] = set()
    obs_per_facility_contributor: dict[tuple[str, str], int] = {}
    facilities_multi_contributor: set[str] = set()
    facility_contributors: dict[str, set[str]] = {}

    for r in records:
        if r.client_type not in {"field_app", "dashboard", "executive"}:
            errors.append(f"client_type inválido: {r.client_type}")
        blob = f"{r.message} {r.contributor}".lower()
        for blocked in REAL_NAMES_BLOCKLIST:
            if blocked in blob:
                errors.append(f"nombre real detectado: {blocked!r}")
        ext = rule_extractor.extract(r.message)
        if not ext.items:
            errors.append(f"sin equipos extraídos: {r.message[:60]!r}")
        if not ext.facility:
            errors.append(f"sin facilidad: {r.message[:60]!r}")
            continue
        facilities.add(ext.facility)
        if ext.country:
            countries.add(ext.country)
        facility_contributors.setdefault(ext.facility, set()).add(r.contributor)
        key = (ext.facility, r.contributor)
        obs_per_facility_contributor[key] = obs_per_facility_contributor.get(key, 0) + 1

    missing = EXPECTED_FACILITIES - facilities
    extra = facilities - EXPECTED_FACILITIES
    if missing:
        errors.append(f"faltan facilidades: {missing}")
    if extra:
        errors.append(f"facilidades no esperadas: {extra}")
    if not countries <= EXPECTED_COUNTRIES:
        errors.append(f"países fuera de catálogo: {countries - EXPECTED_COUNTRIES}")
    if len(countries) < 4:
        errors.append(f"se esperaban >=4 países, hay {len(countries)}: {countries}")

    facilities_multi_contributor = {
        f for f, cs in facility_contributors.items() if len(cs) >= 2
    }
    if len(facilities_multi_contributor) < 3:
        errors.append(
            "se necesitan >=3 facilidades con observaciones de varios "
            "contribuyentes para ejercitar consenso"
        )
    if not any(n >= 2 for n in obs_per_facility_contributor.values()):
        errors.append(
            "se necesita >=1 facilidad observada dos veces por el mismo "
            "contribuyente para ejercitar Reportado"
        )
    return errors


async def _wipe() -> None:
    driver = engine.driver()
    if driver is not None:
        async with driver.session() as session:
            await session.run("MATCH (n) DETACH DELETE n")
    pool = db.pool()
    if pool is not None:
        async with pool.acquire() as conn:
            await conn.execute(
                "TRUNCATE transaction_log, perf_log, equipment_state_log RESTART IDENTITY"
            )
    logger.info("Grafo y logs reiniciados")


async def seed(wipe: bool = False) -> dict[str, int]:
    """Load the dataset through the real extractor + engine pipeline."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    errors = validate_dataset()
    if errors:
        raise SystemExit(f"Dataset inválido:\n  - " + "\n  - ".join(errors))

    await db.init_pool(settings.postgres_dsn)
    await db.ensure_schema()
    await auth_service.ensure_bootstrap_admin()
    # Seed contributors must be real user identities so observations are
    # attributed to actual accounts (capturer role, documented dev password).
    for name in CONTRIBUTORS:
        await auth_service.ensure_user(
            username=contributor_username(name),
            full_name=name,
            role="capturer",
            password=CONTRIBUTOR_PASSWORD,
        )
    engine.init_driver(settings)
    await engine.bootstrap_schema()
    if wipe:
        await _wipe()

    stats = {"observations": 0, "facilities": 0, "equipment": 0, "transactions": 0}
    seen_facilities: set[str] = set()
    for rec in DATASET:
        ext = rule_extractor.extract(rec.message)
        result = await engine.ingest_extraction(ext, rec.contributor, rec.client_type)
        stats["observations"] += 1
        stats["equipment"] += len(result.equipment_ids)
        stats["transactions"] += len(result.transaction_ids)
        if ext.facility and ext.facility not in seen_facilities:
            seen_facilities.add(ext.facility)
            stats["facilities"] += 1
        print(f"  [{rec.contributor}] {ext.facility}: {result.mutation_summary}")

    print(
        "\nSeed completado: %(observations)d observaciones, %(facilities)d facilidades, "
        "%(equipment)d equipos tocados, %(transactions)d transacciones" % stats
    )
    print(
        "Usuarios capturer: "
        + ", ".join(
            f"{contributor_username(n)} / {CONTRIBUTOR_PASSWORD}" for n in CONTRIBUTORS
        )
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga datos sintéticos en SynapseCME")
    parser.add_argument("--wipe", action="store_true", help="reinicia grafo y logs antes de cargar")
    args = parser.parse_args()
    asyncio.run(seed(wipe=args.wipe))


if __name__ == "__main__":
    main()
