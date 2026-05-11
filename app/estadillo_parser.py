import re
import unicodedata
from datetime import date, timedelta
from typing import Optional

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

DIAS_OFFSET = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "domingo": 6,
}

# Strip annotation emojis and any other non-ASCII emoji
_STRIP_EMOJI = re.compile(
    r'[❌‼️]'
    r'|[\U0001F300-\U0001FAFF]'   # misc symbols & pictographs
    r'|[☀-➿]',           # misc symbols, dingbats
)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()


def _parse_fecha_inicio(line: str) -> Optional[date]:
    m = re.search(r'(\d{1,2})\s+([A-Za-záéíóúüÁÉÍÓÚÜ]+)', line)
    if not m:
        return None
    try:
        dia = int(m.group(1))
    except ValueError:
        return None
    mes = MESES_ES.get(_norm(m.group(2)))
    if not mes:
        return None
    today = date.today()
    year = today.year
    try:
        d = date(year, mes, dia)
    except ValueError:
        return None
    # If the date lands more than 30 days in the future, assume it's last year
    # (estadillos históricos que se cargan fuera de plazo)
    if (d - today).days > 30:
        try:
            d = date(year - 1, mes, dia)
        except ValueError:
            pass
    return d


def _parse_personas(names_str: str) -> list[tuple[str, bool]]:
    """
    Parses the names part of a shift line.
    Returns list of (nombre_raw, es_vet_por_convencion).
    Returns empty list if no vet present (slot vacío).

    Conventions:
    - UPPERCASE first word = veterano
    - lowercase first word = voluntario
    - * separates people
    - ❌ / ‼️ are ignored annotations
    """
    cleaned = _STRIP_EMOJI.sub("", names_str).strip()
    if not cleaned:
        return []

    parts = [p.strip() for p in cleaned.split("*") if p.strip()]
    if not parts:
        return []

    result = []
    for part in parts:
        part = re.sub(r'\s*\(.*?\)\s*', '', part).strip()
        if not part or part.lower() == 'visita':
            continue
        words = part.split()
        if not words:
            continue
        # vet if first word is fully uppercase and ≥ 2 chars (avoids lone initials)
        es_vet = words[0].isupper() and len(words[0]) >= 2
        result.append((part, es_vet))

    # If no vet found, the slot is uncovered — return empty
    if not any(es_vet for _, es_vet in result):
        return []

    return result


def parse_estadillo(text: str) -> tuple[Optional[date], list]:
    """
    Parses a pasted estadillo text.

    Returns (fecha_inicio, slots) where slots is:
        [(fecha, franja, [(nombre_raw, es_vet_convencion), ...])]

    An empty inner list means the slot has no vet and should be skipped.
    """
    lines = text.strip().splitlines()

    fecha_inicio = None
    for line in lines[:6]:
        fecha_inicio = _parse_fecha_inicio(line.strip())
        if fecha_inicio:
            break

    slots = []
    current_offset = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Day header: "LUNES:", "MIÉRCOLES:", etc.
        line_norm = _norm(line.rstrip(":").strip())
        if line_norm in DIAS_OFFSET:
            current_offset = DIAS_OFFSET[line_norm]
            continue

        # Shift line: "- Mañana: ..." or "- Tarde: ..."
        m = re.match(r"-\s*(ma[nñ]ana|tarde)\s*:\s*(.*)", line, re.IGNORECASE)
        if m and current_offset is not None and fecha_inicio is not None:
            franja_raw = _norm(m.group(1))
            franja = "manana" if franja_raw.startswith("ma") else "tarde"
            personas = _parse_personas(m.group(2))
            fecha = fecha_inicio + timedelta(days=current_offset)
            slots.append((fecha, franja, personas))

    return fecha_inicio, slots


def buscar_voluntario(todos, nombre_raw: str):
    """Fuzzy lookup: exact name first, then prefix match for nicknames (Esme → Esmeralda)."""
    partes = nombre_raw.strip().split()
    nombre_n = _norm(partes[0])
    inicial = partes[1].upper() if len(partes) > 1 else None

    def _por_inicial(candidatos):
        if not inicial:
            return candidatos
        for longitud in (len(inicial), 1):
            filtrados = [
                v for v in candidatos
                if v.apellido and _norm(v.apellido).startswith(_norm(inicial[:longitud]))
            ]
            if len(filtrados) == 1:
                return filtrados
        return candidatos

    # 1. Exact name match
    candidatos = [v for v in todos if _norm(v.nombre) == nombre_n]

    # 2. Prefix match: "Esme" matches "Esmeralda", or "Esmeralda" matches "Esme" in DB
    if not candidatos:
        candidatos = [
            v for v in todos
            if _norm(v.nombre).startswith(nombre_n) or nombre_n.startswith(_norm(v.nombre))
        ]

    if not candidatos:
        return None
    if len(candidatos) == 1:
        return candidatos[0]

    filtrados = _por_inicial(candidatos)
    return filtrados[0] if len(filtrados) == 1 else None
