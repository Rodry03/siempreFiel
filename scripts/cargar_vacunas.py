import os
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.models import Vacuna

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/protectora")
engine = create_engine(DATABASE_URL)

df = pd.read_sql("""
    select
        p.id as perro_id,
        p.nombre,
        e.vacuna_rabia,   e.proxima_rabia,
        e.vacuna_canigen, e.proxima_canigen,
        e.vacuna_dps,     e.proxima_dps
    from analytics.stg_perros_entrada e
    join public.perros p on p.num_chip = e.num_chip
""", con=engine)

print(f"Perros con datos de vacunas: {len(df)}")

VACUNAS = [
    ("Rabia",   "vacuna_rabia",   "proxima_rabia"),
    ("Canigen", "vacuna_canigen", "proxima_canigen"),
    ("DPS",     "vacuna_dps",     "proxima_dps"),
]

with Session(engine) as session:
    insertadas = 0
    saltadas = 0

    for _, row in df.iterrows():
        for tipo, col_fecha, col_proxima in VACUNAS:
            if pd.isna(row[col_fecha]):
                saltadas += 1
                continue

            ya_existe = session.query(Vacuna).filter_by(
                perro_id=row["perro_id"],
                tipo=tipo,
                fecha_administracion=row[col_fecha],
            ).first()

            if ya_existe:
                saltadas += 1
                continue

            session.add(Vacuna(
                perro_id=int(row["perro_id"]),
                tipo=tipo,
                fecha_administracion=row[col_fecha],
                fecha_proxima=row[col_proxima] if pd.notna(row[col_proxima]) else None,
            ))
            insertadas += 1
            print(f"  OK {row['nombre']} — {tipo} ({row[col_fecha]})")

    session.commit()

print(f"\nInsertadas: {insertadas} | Saltadas (sin fecha o duplicadas): {saltadas}")
