import os
import sys
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

if "--prod" in sys.argv:
    DATABASE_URL = (
        f"postgresql://{os.getenv('DBT_NEON_USER')}:{os.getenv('DBT_NEON_PASSWORD')}"
        f"@{os.getenv('DBT_NEON_HOST')}/{os.getenv('DBT_NEON_DBNAME')}?sslmode=require"
    )
    print("Cargando en PRODUCCIÓN (Neon)...")
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/protectora")
    print("Cargando en LOCAL...")

COLUMNAS = {
    "Nº":              "numero",
    "PERRO":           "perro",
    "RABIA":           "rabia",
    "RECOR":           "recor_rabia",
    "CANIGEN":         "canigen",
    "RECOR.":          "recor_canigen",
    "DPS INTER":       "dps_inter",
    "RECOR..1":        "recor_dps",
    "Nº CHIP":         "num_chip",
    "Nº PASAPORTE":    "num_pasaporte",
    "FEC. NACIMIENTO": "fec_nacimiento",
    "SEXO":            "sexo",
    "F. ENTRADA":      "f_entrada",
    "F.SALIDA":        "f_salida",
    "ESTADO":          "estado",
    "PERRO.1":         "perro_duplicado",
    "CASTRADO":        "castrado",
    "RAZA":            "raza",
    "TAMAÑO":          "tamano",
    "CAPA":            "capa",
    "OBSERVACIONES":   "observaciones",
}

df = pd.read_excel(
    "data/perros.xlsx",
    sheet_name="ACTUALES",
    skiprows=1,
    usecols=range(21),
)

df.columns = df.columns.str.strip()
df = df.rename(columns=COLUMNAS)
df = df.dropna(how="all")
df = df[df["perro"].notna()]

# Deduplicar por chip (mantenemos la fila con numero válido)
df_con_chip = (
    df[df["num_chip"].notna()]
    .sort_values("numero", na_position="last")
    .drop_duplicates(subset=["num_chip"], keep="first")
)
df_sin_chip = df[df["num_chip"].isna()]
df = pd.concat([df_con_chip, df_sin_chip]).reset_index(drop=True)

print(f"Filas a cargar: {len(df)}")
print(df[["numero", "perro", "raza", "sexo", "castrado", "estado"]].to_string())

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
    conn.commit()

with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS raw.perros_xlsx CASCADE"))
    conn.commit()

df.to_sql("perros_xlsx", schema="raw", con=engine, if_exists="replace", index=False)

print("\nCarga completada: raw.perros_xlsx")

# --- ADOPTADOS ---
COLUMNAS_ADOPTADOS = {
    "PERRO":            "perro",
    "RABIA":            "rabia",
    "RECORDATORIO":     "recor_rabia",
    "CANIGEN":          "canigen",
    "RECOR.":           "recor_canigen",
    "DPS INTER":        "dps_inter",
    "RECOR..1":         "recor_dps",
    "Nº CHIP":          "num_chip",
    "Nº PASAPORTE":     "num_pasaporte",
    "FEC. NACIMIENTO":  "fec_nacimiento",
    "SEXO":             "sexo",
    "FECHA ENTRADA":    "f_entrada",
    "FECHA DE SALIDA":  "f_salida",
    "ESTADO":           "estado",
}

df_ad = pd.read_excel(
    "data/perros.xlsx",
    sheet_name="ADOPTADOS",
    skiprows=1,
    usecols=range(14),
)

df_ad.columns = df_ad.columns.str.strip()
df_ad = df_ad.rename(columns=COLUMNAS_ADOPTADOS)
df_ad = df_ad.dropna(how="all")
df_ad = df_ad[df_ad["perro"].notna()]

# Limpiar espacios en chips
df_ad["num_chip"] = df_ad["num_chip"].apply(
    lambda x: str(x).replace(" ", "").strip() if pd.notna(x) else x
)

df_ad.to_sql("perros_adoptados", schema="raw", con=engine, if_exists="replace", index=False)

print(f"Carga completada: raw.perros_adoptados ({len(df_ad)} filas)")
