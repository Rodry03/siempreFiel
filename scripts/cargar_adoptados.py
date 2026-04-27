import os
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.models import Perro, Ubicacion, Vacuna, Raza, EstadoPerro, TipoUbicacion, Sexo

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/protectora")
engine = create_engine(DATABASE_URL)

df = pd.read_sql(
    "SELECT * FROM analytics.stg_perros_adoptados",
    con=engine
)

print(f"Adoptados a cargar: {len(df)}")

VACUNAS = [
    ("Rabia",   "vacuna_rabia",   "proxima_rabia"),
    ("Canigen", "vacuna_canigen", "proxima_canigen"),
    ("DPS",     "vacuna_dps",     "proxima_dps"),
]

LOTE = 100

with Session(engine) as session:
    razas = {r.nombre.lower(): r.id for r in session.query(Raza).all()}
    raza_otro_id = razas["otro"]

    chips_app = {c for (c,) in session.query(Perro.num_chip).filter(Perro.num_chip.isnot(None)).all()}
    pasaportes_app = {p for (p,) in session.query(Perro.num_pasaporte).filter(Perro.num_pasaporte.isnot(None)).all()}

    insertados = 0
    saltados = 0

    for _, row in df.iterrows():
        if row["num_chip"] and row["num_chip"] in chips_app:
            saltados += 1
            continue

        if row["num_pasaporte"] and row["num_pasaporte"] in pasaportes_app:
            saltados += 1
            continue

        # Necesitamos al menos una fecha
        fecha_entrada = row["fecha_entrada"] if pd.notna(row["fecha_entrada"]) else None
        fecha_adopcion = row["fecha_adopcion"] if pd.notna(row["fecha_adopcion"]) else None
        fecha_ref = fecha_entrada or fecha_adopcion
        if not fecha_ref:
            saltados += 1
            continue

        perro = Perro(
            nombre=row["nombre"],
            raza_id=raza_otro_id,
            fecha_nacimiento=row["fecha_nacimiento"] if pd.notna(row["fecha_nacimiento"]) else None,
            sexo=Sexo(row["sexo"]),
            esterilizado=False,
            num_chip=row["num_chip"] if pd.notna(row["num_chip"]) else None,
            num_pasaporte=row["num_pasaporte"] if pd.notna(row["num_pasaporte"]) else None,
            fecha_entrada=fecha_ref,
            estado=EstadoPerro.adoptado,
        )
        session.add(perro)
        session.flush()

        session.add(Ubicacion(
            perro_id=perro.id,
            tipo=TipoUbicacion.adoptado,
            fecha_inicio=fecha_adopcion or fecha_ref,
        ))

        for tipo, col_fecha, col_proxima in VACUNAS:
            if pd.notna(row[col_fecha]):
                session.add(Vacuna(
                    perro_id=perro.id,
                    tipo=tipo,
                    fecha_administracion=row[col_fecha],
                    fecha_proxima=row[col_proxima] if pd.notna(row[col_proxima]) else None,
                ))

        if row["num_chip"]:
            chips_app.add(row["num_chip"])
        if row["num_pasaporte"]:
            pasaportes_app.add(row["num_pasaporte"])

        insertados += 1
        if insertados % LOTE == 0:
            session.commit()
            print(f"  {insertados} insertados...")

    session.commit()

print(f"\nInsertados: {insertados} | Saltados: {saltados}")
