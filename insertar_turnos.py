import re
import unicodedata
from datetime import date
from app.database import SessionLocal
from app.models import Voluntario, TurnoVoluntario, EstadoTurno

ET = EstadoTurno

SEMANA = {
    "lunes":     date(2026, 3, 16),
    "martes":    date(2026, 3, 17),
    "miercoles": date(2026, 3, 18),
    "jueves":    date(2026, 3, 19),
    "viernes":   date(2026, 3, 20),
    "sabado":    date(2026, 3, 21),
    "domingo":   date(2026, 3, 22),
}

# (fecha, franja, [(nombre, role, estado)])
# lista vacía = sin veterano, no se inserta nada
# ❌ tras nombres en mayúscula = anotación, turno sí realizado
# ❌ sin veterano = lista vacía
# Visita = omitido
ESTADILLO = [
    # LUNES
    (SEMANA["lunes"], "manana", [
        ("ALEJANDRA S", "vet", ET.realizado),
        ("Casandra R",  "vol", ET.realizado),
    ]),
    (SEMANA["lunes"], "tarde", []),              # ❌(*Marina G)❌ sin veterano

    # MARTES
    (SEMANA["martes"], "manana", [
        ("MIGUEL D", "vet", ET.realizado),
        ("Paula E",  "vol", ET.realizado),
    ]),
    (SEMANA["martes"], "tarde", [
        ("RAFA C",   "vet", ET.realizado),
        ("Lucia V",  "vol", ET.realizado),
        ("Jimena R", "vol", ET.realizado),
    ]),

    # MIERCOLES
    (SEMANA["miercoles"], "manana", [
        ("ANDREA H",   "vet", ET.realizado),
        ("Casandra R", "vol", ET.realizado),
    ]),
    (SEMANA["miercoles"], "tarde", [
        ("ROCIO C",   "vet", ET.realizado),
        ("Sofia RG",  "vol", ET.realizado),
        ("Valeria A", "vol", ET.realizado),
    ]),

    # JUEVES
    (SEMANA["jueves"], "manana", [
        ("LORENA R",  "vet", ET.realizado),
        ("Uxue M",    "vol", ET.realizado),
        ("Claudia C", "vol", ET.realizado),
    ]),
    (SEMANA["jueves"], "tarde", [
        ("MER V",    "vet", ET.realizado),
        ("Sofia RM", "vol", ET.realizado),   # vet actuando como vol en este slot
    ]),

    # VIERNES
    (SEMANA["viernes"], "manana", []),         # ❌(*Irene P)❌ sin veterano
    (SEMANA["viernes"], "tarde", [
        ("IZADI M", "vet", ET.realizado),
        ("Noah C",  "vol", ET.realizado),
    ]),

    # SABADO
    (SEMANA["sabado"], "manana", [
        ("SUSANA F", "vet", ET.realizado),
        ("Javier V", "vol", ET.realizado),
        ("Sam F",    "vol", ET.realizado),
    ]),
    (SEMANA["sabado"], "tarde", [
        ("GUILLERMO C", "vet", ET.realizado),
        ("Marta S",     "vol", ET.realizado),
        ("Paula E",     "vol", ET.medio_turno),  # (hasta las 19-20) → medio turno
    ]),

    # DOMINGO
    (SEMANA["domingo"], "manana", [
        ("SARA MD",   "vet", ET.realizado),
        ("Irene P",   "vol", ET.realizado),
        ("Luis C",    "vol", ET.realizado),
        ("Mihaela M", "vol", ET.realizado),
    ]),
    (SEMANA["domingo"], "tarde", []),          # ❌❌ sin cubrir
]


def norm(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()


def buscar(todos: list[Voluntario], nombre_raw: str) -> Voluntario | None:
    nombre_raw = re.sub(r'\s*\(.*?\)\s*', '', nombre_raw).strip()
    partes = nombre_raw.split()
    nombre_n = norm(partes[0])
    inicial = partes[1].upper() if len(partes) > 1 else None

    candidatos = [v for v in todos if norm(v.nombre) == nombre_n]
    if not candidatos:
        return None
    if len(candidatos) == 1:
        return candidatos[0]
    if inicial:
        for longitud in (len(inicial), 1):
            filtrados = [v for v in candidatos if v.apellido and norm(v.apellido).startswith(norm(inicial[:longitud]))]
            if len(filtrados) == 1:
                return filtrados[0]
    return None


def insertar(db, voluntario: Voluntario, fecha: date, franja: str, estado: EstadoTurno) -> bool:
    existe = db.query(TurnoVoluntario).filter(
        TurnoVoluntario.voluntario_id == voluntario.id,
        TurnoVoluntario.fecha == fecha,
        TurnoVoluntario.franja == franja,
    ).first()
    if existe:
        print(f"  OMITIDO (ya existe): {voluntario.nombre} {voluntario.apellido} — {fecha} {franja}")
        return False
    db.add(TurnoVoluntario(
        voluntario_id=voluntario.id,
        fecha=fecha,
        franja=franja,
        estado=estado,
    ))
    return True


db = SessionLocal()
try:
    todos = db.query(Voluntario).all()
    insertados = 0
    no_encontrados = []

    for fecha, franja, personas in ESTADILLO:
        if not personas:
            print(f"  SKIP (sin cubrir): {fecha} {franja}")
            continue

        for nombre_raw, role, estado in personas:
            nombre_limpio = re.sub(r'\s*\(.*?\)\s*', '', nombre_raw).strip()
            v = buscar(todos, nombre_raw)
            if v:
                if insertar(db, v, fecha, franja, estado):
                    estado_label = "½" if estado == ET.medio_turno else "1"
                    print(f"  + {v.nombre} {v.apellido} — {fecha} {franja} [{role}] ({estado_label})")
                    insertados += 1
            else:
                no_encontrados.append(f"[{role}] '{nombre_limpio}' ({fecha} {franja})")

    db.commit()
    print(f"\n{insertados} turno(s) insertado(s).")
    if no_encontrados:
        print(f"\nNo encontrados en BD ({len(no_encontrados)}):")
        for n in no_encontrados:
            print(f"  - {n}")
finally:
    db.close()
