import os
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.models import Perro, Ubicacion, Raza, EstadoPerro, TipoUbicacion, Sexo

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/protectora")
engine = create_engine(DATABASE_URL)

df = pd.read_sql(
    "SELECT * FROM analytics.mart_perros_a_cargar WHERE estado_carga = 'listo'",
    con=engine
)

print(f"Perros a cargar: {len(df)}")

with Session(engine) as session:
    razas = {r.nombre.lower(): r.id for r in session.query(Raza).all()}

    insertados = 0
    saltados = 0

    for _, row in df.iterrows():
        if row["num_chip"] and session.query(Perro).filter_by(num_chip=row["num_chip"]).first():
            print(f"  SKIP {row['nombre']}: ya existe en la app")
            saltados += 1
            continue

        raza_id = razas.get(row["raza"].lower())
        if not raza_id:
            print(f"  SKIP {row['nombre']}: raza '{row['raza']}' no encontrada")
            saltados += 1
            continue

        perro = Perro(
            nombre=row["nombre"],
            raza_id=raza_id,
            fecha_nacimiento=row["fecha_nacimiento"] if pd.notna(row["fecha_nacimiento"]) else None,
            sexo=Sexo(row["sexo"]),
            esterilizado=bool(row["esterilizado"]),
            num_chip=row["num_chip"] if pd.notna(row["num_chip"]) else None,
            num_pasaporte=row["num_pasaporte"] if pd.notna(row["num_pasaporte"]) else None,
            fecha_entrada=row["fecha_entrada"],
            estado=EstadoPerro.activo,
            color=row["color"] if pd.notna(row["color"]) else None,
            notas=row["notas"] if pd.notna(row["notas"]) else None,
        )
        session.add(perro)
        session.flush()

        ubicacion = Ubicacion(
            perro_id=perro.id,
            tipo=TipoUbicacion(row["tipo_ubicacion"]),
            fecha_inicio=row["fecha_entrada"],
        )
        session.add(ubicacion)
        insertados += 1
        print(f"  OK {row['nombre']} ({row['raza']}) — {row['tipo_ubicacion']}")

    session.commit()

print(f"\nInsertados: {insertados} | Saltados: {saltados}")
