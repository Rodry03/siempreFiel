import os
import re
import sys
import unicodedata
from datetime import date

import openpyxl
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.models import Perro, Raza, EstadoPerro, Sexo

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/protectora")
engine = create_engine(DATABASE_URL)

EXCEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "perros.xlsx")


def norm(s: str) -> str:
    """Lowercase, strip accents, collapse spaces."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


# Razas from Excel that need to be created in DB (normalized key → display name)
RAZAS_NUEVAS = {
    norm("AMERICAN BULLY POCKET"):               "American Bully Pocket",
    norm("AMERICAN STAFFORD X PITBULL"):         "American Stafford X Pitbull",
    norm("BODEGUERO ANDALUZ"):                   "Bodeguero Andaluz",
    norm("BODEGUERO X PASTOR ALEMAN"):           "Bodeguero X Pastor Alemán",
    norm("BOXER X PASTOR BELGA"):                "Boxer X Pastor Belga",
    norm("BRETON X POINTER"):                    "Bretón X Pointer",
    norm("GOLDEN X PASTOR ALEMAN"):              "Golden X Pastor Alemán",
    norm("MASTIN X BORDER COLLIE"):              "Mastín X Border Collie",
    norm("MINI PINCHER"):                        "Mini Pinscher",
    "p aleman x alano":                          "Pastor Alemán X Alano",  # "P. ALEMÁN X ALANO"
    norm("PODENCO ANDALUZ"):                     "Podenco Andaluz",
    norm("PODENCO ANDALUZ X TERRIER CAZADOR"):   "Podenco Andaluz X Terrier Cazador",
    norm("SAN BERNARDO"):                        "San Bernardo",
    norm("TECKEL X LABRADOR"):                   "Teckel X Labrador",
    norm("X BEAGLE"):                            "X Beagle",
    norm("X BODEGUERO"):                         "X Bodeguero",
    norm("X BULLDOG FRANCES"):                   "X Bulldog Francés",
    norm("X LABRADOR"):                          "X Labrador",
    norm("X MASTIN"):                            "X Mastín",
    norm("X MINI PINCHER"):                      "X Mini Pinscher",
}


def parsear_chip(val) -> str | None:
    if not val:
        return None
    s = str(val).strip()
    if re.match(r"^\d+$", s):
        return s
    return None


def parsear_pasaporte(val) -> str | None:
    if not val:
        return None
    s = str(val).strip()
    # Solo válido si empieza por código de país (letras) seguido de dígitos
    if re.match(r"^[A-Z]{2}\d+$", s):
        return s
    return None


def parsear_sexo(val) -> Sexo | None:
    if not val:
        return None
    s = str(val).strip().upper()
    if s == "MACHO":
        return Sexo.macho
    if s == "HEMBRA":
        return Sexo.hembra
    return None


def parsear_fecha(val) -> date | None:
    if not val:
        return None
    if isinstance(val, date):
        return val.date() if hasattr(val, "date") else val
    return None


wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
ws = wb["RESERVADOS"]
filas = [r for r in ws.iter_rows(min_row=4, values_only=True) if r[1] and str(r[1]).strip()]

print(f"Perros en pestaña RESERVADOS: {len(filas)}")

with Session(engine) as session:
    # Construir índice de razas DB (normalizado → id)
    razas_db = {norm(r.nombre): r.id for r in session.query(Raza).all()}
    raza_otro_id = razas_db[norm("Otro")]

    # Crear razas nuevas que no existan (idempotente)
    for norm_key, display_name in RAZAS_NUEVAS.items():
        norm_display = norm(display_name)
        if norm_key in razas_db:
            continue
        if norm_display in razas_db:
            razas_db[norm_key] = razas_db[norm_display]
            continue
        nueva = Raza(nombre=display_name)
        session.add(nueva)
        session.flush()
        razas_db[norm_key] = nueva.id
        razas_db[norm_display] = nueva.id
        print(f"  + Raza creada: {display_name}")
    session.commit()

    # Chips y pasaportes ya en DB
    chips_db = {c for (c,) in session.query(Perro.num_chip).filter(Perro.num_chip.isnot(None)).all()}
    chips_procesados: set[str] = set()

    insertados = 0
    saltados = 0

    for fila in filas:
        nombre_raw = str(fila[1]).strip()
        chip = parsear_chip(fila[8])
        pasaporte = parsear_pasaporte(fila[9])
        fecha_nacimiento = parsear_fecha(fila[10])
        sexo = parsear_sexo(fila[11])
        fecha_entrada = parsear_fecha(fila[12])
        castrado_raw = str(fila[16]).strip().upper() if fila[16] else "NO"
        raza_raw = str(fila[17]).strip() if fila[17] else None

        # Deduplicar por chip dentro del propio Excel
        if chip:
            if chip in chips_db or chip in chips_procesados:
                saltados += 1
                continue
            chips_procesados.add(chip)

        if not sexo:
            print(f"  SKIP {nombre_raw}: sexo desconocido")
            saltados += 1
            continue

        if not fecha_entrada:
            fecha_entrada = date.today()

        # PPP y nombre limpio
        ppp = bool(re.search(r"\(ppp\)", nombre_raw, re.IGNORECASE))
        nombre = re.sub(r"\s*\(.*?\)", "", nombre_raw).strip().upper()

        # Raza
        raza_id = raza_otro_id
        if raza_raw:
            raza_norm = norm(raza_raw)
            raza_id = razas_db.get(raza_norm, raza_otro_id)

        esterilizado = castrado_raw == "SI"

        perro = Perro(
            nombre=nombre,
            raza_id=raza_id,
            fecha_nacimiento=fecha_nacimiento,
            sexo=sexo,
            esterilizado=esterilizado,
            ppp=ppp,
            num_chip=chip,
            num_pasaporte=pasaporte,
            fecha_entrada=fecha_entrada,
            estado=EstadoPerro.reservado,
        )
        session.add(perro)
        insertados += 1
        print(f"  OK {nombre:<25} ppp={ppp} chip={chip or '—'}")

    session.commit()

print(f"\nInsertados: {insertados} | Saltados: {saltados}")
