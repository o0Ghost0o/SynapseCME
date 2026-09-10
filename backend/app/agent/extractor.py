"""Deterministic rule-based Spanish extractor (fallback when QVAC is down).

Parses conversational field-engineer observations into a structured
ExtractionResult using regex/keyword matching. Pure functions: no I/O.
"""

from __future__ import annotations

import re

from app.models import EquipmentItem, ExtractionResult, ParameterExtraction

# modality keyword -> canonical code
MODALITY_KEYWORDS: list[tuple[str, str]] = [
    (r"\bresonancia\w*\b|\brm\b", "MR"),
    (r"\btomógrafo\w*\b|\btomografia\w*\b|\btc\b|\bct\b", "CT"),
    (r"\brayos?\s*x\b|\bradiografía\w*\b|\brx\b|\bxr\b", "XR"),
    (r"\bultrasonido\w*\b|\becografía\w*\b|\bus\b|\bultra\w*\b", "UL"),
    (r"\bmamografía\w*\b|\bmammo\b", "MG"),
    (r"\bfluoroscopia\w*\b|\bc-arm\b|\barco\sen\s*c\b", "RF"),
]

SPANISH_NUMBERS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}

MANUFACTURERS = [
    "Siemens", "GE", "Philips", "Canon", "Toshiba", "Hitachi", "Fujifilm",
    "Samsung", "Mindray", "Hologic", "Carestream",
]

COUNTRIES = [
    "Panamá", "Mexico", "México", "Colombia", "Argentina", "Chile", "Perú",
    "Peru", "Ecuador", "Brasil", "Costa Rica", "Guatemala", "España", "Spain",
    "Francia", "Alemania", "Estados Unidos", "USA", "Bolivia", "Uruguay",
    "Venezuela", "Honduras", "El Salvador", "Nicaragua", "Cuba", "RD",
]

# City -> country, used to resolve cities that appear only inside a facility
# name ("Hospital General de Valencia") or without an explicit country.
# Ambiguous names shared by several countries (p.ej. Córdoba) se omiten.
CITY_COUNTRY: dict[str, str] = {
    # España
    "Madrid": "España", "Barcelona": "España", "Valencia": "España",
    "Sevilla": "España", "Zaragoza": "España", "Málaga": "España",
    "Bilbao": "España", "Murcia": "España", "Alicante": "España",
    "Granada": "España", "Valladolid": "España", "Vigo": "España",
    # Panamá
    "Ciudad de Panamá": "Panamá", "Panamá": "Panamá", "Colón": "Panamá",
    # Colombia
    "Bogotá": "Colombia", "Medellín": "Colombia", "Cali": "Colombia",
    "Barranquilla": "Colombia", "Cartagena": "Colombia",
    # México
    "Ciudad de México": "México", "Guadalajara": "México",
    "Monterrey": "México", "Puebla": "México", "Mérida": "México",
    "Cancún": "México", "Tijuana": "México",
    # Argentina
    "Buenos Aires": "Argentina", "Rosario": "Argentina", "Mendoza": "Argentina",
    # Chile
    "Santiago": "Chile", "Valparaíso": "Chile", "Concepción": "Chile",
    # Perú
    "Lima": "Perú", "Arequipa": "Perú",
    # Ecuador
    "Quito": "Ecuador", "Guayaquil": "Ecuador",
    # Brasil
    "São Paulo": "Brasil", "Río de Janeiro": "Brasil", "Brasilia": "Brasil",
    # Resto de LatAm
    "San José": "Costa Rica", "Ciudad de Guatemala": "Guatemala",
    "Montevideo": "Uruguay", "Caracas": "Venezuela", "Maracaibo": "Venezuela",
    "La Paz": "Bolivia", "Santo Domingo": "RD",
    "Tegucigalpa": "Honduras", "San Pedro Sula": "Honduras",
    "San Salvador": "El Salvador", "Managua": "Nicaragua",
    "La Habana": "Cuba",
    # Otros
    "Miami": "Estados Unidos", "Nueva York": "Estados Unidos",
    "Houston": "Estados Unidos", "Berlín": "Alemania", "Múnich": "Alemania",
}

# High-value modalities that justify a follow-up when manufacturer is unknown.
HIGH_VALUE_MODALITIES = {"MR", "CT"}

# --- Technical parameters --------------------------------------------------
# Keyword -> canonical parameter name. Status is INFERRED from nearby words
# (see PARAM_STATUS_KEYWORDS), never copied from the text.
PARAM_KEYWORDS: list[tuple[str, str]] = [
    (r"\bhelio\b", "nivel de helio"),
    (r"\bcorriente\w*", "corriente"),
    (r"\bvoltaje\b|\btensi[oó]n\b", "voltaje"),
    (r"\btemperatura\w*", "temperatura"),
    (r"\bpresi[oó]n\w*", "presión"),
    (r"\bcortes?\b", "cortes de tubo"),
    (r"\btasa\s+de\s+dosis\b", "tasa de dosis"),
    (r"\bcalentamiento\s+del\s+[aá]nodo\b", "calentamiento del ánodo"),
    (r"\bnivel\s+de\s+ruido\b", "nivel de ruido"),
]

# Priority order matters: the first table that matches wins.
PARAM_STATUS_KEYWORDS: list[tuple[str, str]] = [
    (r"fuera\s+de\s+rango|sobrecarg\w+|cr[ií]tic\w+|falla\w*|no\s+funciona|roto\w*",
     "critical"),
    (r"\balto\w*|\bbajo\w*|inestable|fluctuante\w*|intermitente|desgastad\w*|"
     r"al\s+l[ií]mite", "warning"),
    (r"nominal|correcto\w*|dentro\s+de\s+(?:su\s+)?rango|estable|sin\s+desviaciones?|"
     r"normal\b|[oó]ptimo\w*", "ok"),
]

# Número + unidad técnica. "millones de" escala el valor (cortes de tubo).
# Las unidades de una letra van sin IGNORECASE para no capturar el artículo "a".
NUMBER_VALUE_RE = re.compile(
    r"(?<![\d-])(\d+(?:[.,]\d+)?)\s*(?i:(millones?\s+de\s+))?"
)
UNIT_VALUE_RE = re.compile(
    r"(%|mA|µA|kV|MV|kW|MW|MU/min|[WVAL]|°C|ºC|bar|psi|horas?|cortes?)(?![\w%])"
)
# Magnitud que PRECEDE al keyword ("con 1.2 millones de cortes"): número con
# escala y/o unidad pegado al final de la ventana previa.
BACKWARD_VALUE_RE = re.compile(
    r"(?<![\d-])(\d+(?:[.,]\d+)?)\s*(?i:(millones?\s+de\s+)?)"
    r"(%|mA|µA|kV|MV|kW|MW|MU/min|[WVAL]|°C|ºC|bar|psi|horas?|cortes?)?\s*$"
)

# Ventana (caracteres tras el keyword) donde se buscan valor y estado.
PARAMETER_WINDOW = 80

FACILITY_RE = re.compile(
    r"\b(Hospital|Clínica|Clinica|Centro\s+Médico|Centro\s+Medico|"
    r"Centro\s+de\s+Salud|Instituto|Maternidad)\s+"
    r"((?:(?:[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ.-]*|del?|la|las|los|y)\s+){1,5})",
    re.UNICODE,
)
AGE_RE = re.compile(r"(?:como\s+|de\s+|casi\s+|aprox\.\s*)?(\d{1,2})\s*años?", re.IGNORECASE)
QTY_DIGIT_RE = re.compile(
    r"(\d{1,3})\s*(?:resonancias?\w*|tomógrafos?\w*|tomografos?\w*|tomografías?\w*"
    r"|rayos?\s*x|radiografías?\w*|ultrasonidos?\w*|ecografías?\w*|\brms?\b|\bcts?\b|\btcs?\b|\burs?\b)",
    re.IGNORECASE,
)
QTY_WORD_RE = re.compile(
    r"\b(un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+"
    r"(?:resonancias?\w*|tomógrafos?\w*|tomografos?\w*|tomografías?\w*"
    r"|rayos?\s*x|radiografías?\w*|ultrasonidos?\w*|ecografías?\w*|\brm\b|\bct\b|\btc\b|\bus\b)",
    re.IGNORECASE,
)


def _detect_modalities(text: str) -> list[str]:
    lowered = f" {text.lower()} "
    found: list[str] = []
    for pattern, code in MODALITY_KEYWORDS:
        if re.search(pattern, lowered):
            if code not in found:
                found.append(code)
    return found


def _detect_quantities(text: str) -> dict[str, int]:
    """Map modality -> quantity mentioned (max of digits vs number words).

    Number-word mentions like "una RM tiene 8 años" refer to units already
    counted ("vi 3 resonancias"), so we take the max rather than the sum.
    """
    lowered = text.lower()
    digits: dict[str, int] = {}
    words: dict[str, int] = {}

    def bump(bucket: dict[str, int], code: str, n: int) -> None:
        bucket[code] = max(bucket.get(code, 0), n)

    for match in QTY_DIGIT_RE.finditer(lowered):
        code = _classify_noun(match.group(0))
        if code:
            bump(digits, code, int(match.group(1)))

    for match in QTY_WORD_RE.finditer(lowered):
        n = SPANISH_NUMBERS.get(match.group(1).lower())
        code = _classify_noun(match.group(0))
        if n and code:
            bump(words, code, n)

    return {code: max(digits.get(code, 0), words.get(code, 0)) or 1 for code in set(digits) | set(words)}


def _classify_noun(fragment: str) -> str | None:
    for pattern, code in MODALITY_KEYWORDS:
        if re.search(pattern, fragment):
            return code
    return None


def _detect_facility(text: str) -> str | None:
    match = FACILITY_RE.search(text)
    if match:
        return f"{match.group(1)} {match.group(2).strip()}".strip()
    return None


def detect_facility(text: str) -> str | None:
    """Public wrapper: facility name when the text mentions one, else None."""
    return _detect_facility(text)


def _detect_country(text: str) -> str | None:
    lowered = text.lower()
    for country in COUNTRIES:
        if country.lower() in lowered:
            return "México" if country == "Mexico" else country
    return None


def _detect_city(text: str, facility: str | None = None) -> str | None:
    """'en <City>, <Country>' or '<Facility> en <City>' pattern (multi-word cities)."""
    country_names = {c.lower() for c in COUNTRIES}
    word = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñ]*"
    seq = rf"{word}(?:\s+(?:del?|la|las|los|y)\s+{word}|\s+{word})*"
    match = re.search(rf"\ben\s+({seq})\s*,", text)
    if match and match.group(1).lower() not in country_names:
        return match.group(1)
    match = re.search(
        rf"\ben\s+({word}(?:\s+{word})*)(?=\s+(?:vi\b|hay\b|tiene\b|cuenta\b|,|$))",
        text,
    )
    if match and match.group(1).lower() not in country_names:
        return match.group(1)
    # Ciudad embebida en el nombre de la instalación:
    # "Hospital General de Valencia" -> Valencia.
    if facility:
        match = re.search(rf"\bde\s+({seq})$", facility)
        if match:
            city = match.group(1)
            if city in CITY_COUNTRY:
                return city
    # Último recurso: gazetteer sobre el texto completo ("estoy en Bogotá").
    # Puede falsarse positivo con hospitales nombrados por un santo/ciudad,
    # pero solo se usa cuando los patrones explícitos no encontraron nada.
    for city in sorted(CITY_COUNTRY, key=len, reverse=True):
        if re.search(rf"\b{re.escape(city)}\b", text, re.IGNORECASE):
            return city
    return None


def _detect_age(text: str) -> float | None:
    match = AGE_RE.search(text)
    if match:
        return float(match.group(1))
    return None


def _detect_manufacturer(text: str) -> str | None:
    lowered = text.lower()
    for mfr in MANUFACTURERS:
        if mfr.lower() in lowered:
            return mfr
    return None


def _parameter_target(
    window: str, items: list[EquipmentItem]
) -> EquipmentItem | None:
    """Item al que se refiere la ventana: el de cuya modalidad se habla ahí."""
    lowered = window.lower()
    for item in items:
        for pattern, code in MODALITY_KEYWORDS:
            if code == item.modality and re.search(pattern, lowered):
                return item
    return items[0] if items else None


def _extract_magnitude(
    sentence: str, keyword: re.Match[str]
) -> tuple[float | int | None, str | None]:
    """Número con unidad (o con 'millones de') tras el keyword; si no, antes."""
    forward = sentence[keyword.start() : keyword.start() + PARAMETER_WINDOW]
    for match in NUMBER_VALUE_RE.finditer(forward):
        scale = match.group(2)
        unit_match = UNIT_VALUE_RE.match(forward, match.end())
        if not scale and not unit_match:
            continue
        unit = unit_match.group(1) if unit_match else None
        value = float(match.group(1).replace(",", "."))
        if scale:
            value = round(value * 1_000_000, 6)
            unit = unit or "cortes"
        return (int(value) if value.is_integer() else value), unit
    backward = sentence[max(0, keyword.start() - 40) : keyword.start()]
    match = BACKWARD_VALUE_RE.search(backward)
    if match and (match.group(2) or match.group(3)):
        value = float(match.group(1).replace(",", "."))
        unit = match.group(3)
        if match.group(2):
            value = round(value * 1_000_000, 6)
            unit = unit or "cortes"
        return (int(value) if value.is_integer() else value), unit
    return None, None


def _infer_parameter_status(window: str) -> str | None:
    lowered = window.lower()
    for pattern, status in PARAM_STATUS_KEYWORDS:
        if re.search(pattern, lowered):
            return status
    return None


def _detect_parameters(message: str, items: list[EquipmentItem]) -> None:
    """Attach ParameterExtraction entries to items from technical magnitudes."""
    if not items:
        return
    for sentence in re.split(r"[.!?]\s+", message):
        for pattern, name in PARAM_KEYWORDS:
            keyword = re.search(pattern, sentence, re.IGNORECASE)
            if keyword is None:
                continue
            start = max(0, keyword.start() - 25)
            window = sentence[start : keyword.start() + PARAMETER_WINDOW]
            target = _parameter_target(window, items)
            if target is None or any(p.name == name for p in target.parameters):
                continue
            value, unit = _extract_magnitude(sentence, keyword)
            target.parameters.append(
                ParameterExtraction(
                    name=name,
                    value=value,
                    unit=unit,
                    status=_infer_parameter_status(window),
                )
            )


def build_followup(ext: ExtractionResult) -> str | None:
    """Targeted follow-up question for missing high-value fields (Spanish)."""
    high_value = [i for i in ext.items if i.modality in HIGH_VALUE_MODALITIES]
    if high_value and any(not i.manufacturer for i in high_value):
        names = " o ".join(sorted({i.modality for i in high_value if not i.manufacturer}))
        facility = f" en {ext.facility}" if ext.facility else ""
        return (
            f"¿Sabes qué fabricante tiene {names}{facility}? "
            "Ayuda mucho para completar la base de equipos."
        )
    if not ext.facility:
        return "¿En qué hospital o clínica hiciste la visita?"
    return None


def extract(message: str) -> ExtractionResult:
    modalities = _detect_modalities(message)
    quantities = _detect_quantities(message)
    facility = _detect_facility(message)
    country = _detect_country(message)
    city = _detect_city(message, facility)
    if country is None and city is not None:
        country = CITY_COUNTRY.get(city)
    age = _detect_age(message)
    manufacturer = _detect_manufacturer(message)

    items: list[EquipmentItem] = []
    for code in modalities:
        qty = quantities.get(code, 1)
        item_age = age if code == "MR" and age is not None else None
        items.append(
            EquipmentItem(
                modality=code,
                manufacturer=manufacturer,
                quantity=qty,
                age_years=item_age,
                confidence=0.6 if quantities.get(code) else 0.45,
            )
        )
    _detect_parameters(message, items)

    missing: list[str] = []
    if not facility:
        missing.append("facility")
    if not country:
        missing.append("country")
    if any(not i.manufacturer for i in items if i.modality in HIGH_VALUE_MODALITIES):
        missing.append("manufacturer")

    ext = ExtractionResult(
        facility=facility,
        city=city,
        country=country,
        items=items,
        missing_fields=missing,
        confidence=0.6 if items else 0.3,
        raw=message,
        extractor="rule",
    )
    ext.followup = build_followup(ext)
    return ext
