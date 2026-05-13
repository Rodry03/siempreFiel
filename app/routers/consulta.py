import os
import re
import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.auth import get_current_user, require_not_veterano
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/consulta",
    tags=["consulta"],
    dependencies=[Depends(get_current_user), Depends(require_not_veterano)],
)

_SCHEMA = """
Tablas de la base de datos PostgreSQL de la protectora de perros "Siempre Fiel":

perros (id, nombre TEXT [siempre en MAYÚSCULAS], raza_id→razas.id, fecha_nacimiento DATE, sexo TEXT('macho'/'hembra'), esterilizado BOOL, ppp BOOL, num_chip TEXT, color TEXT, fecha_entrada DATE, estado TEXT('libre'/'reservado'/'adoptado'/'fallecido'), fecha_adopcion DATE, fecha_reserva DATE, notas TEXT)
  NOTA: estado 'libre' o 'reservado' = activo en el refugio.

razas (id, nombre TEXT)

ubicaciones (id, perro_id→perros.id, tipo TEXT('refugio'/'acogida'/'residencia'/'casa_adoptiva'), fecha_inicio DATE, fecha_fin DATE [NULL=ubicación actual], nombre_contacto TEXT, telefono_contacto TEXT)

voluntarios (id, nombre TEXT, apellido TEXT, dni TEXT, email TEXT, telefono TEXT, perfil TEXT('directiva'/'apoyo_en_junta'/'veterano'/'voluntario'/'guagua'/'eventos'/'colaboradores'), fecha_alta DATE, activo BOOL, ppp BOOL, fecha_veterano DATE, fecha_fin_veterano DATE, teaming BOOL)

turnos_voluntarios (id, voluntario_id→voluntarios.id, fecha DATE, franja TEXT('manana'/'tarde'), estado TEXT('realizado'/'medio_turno'/'falta_justificada'/'falta_injustificada'/'no_apuntado'))

vacunas (id, perro_id→perros.id, tipo TEXT, fecha_administracion DATE, fecha_proxima DATE, veterinario TEXT)

medicaciones_perro (id, perro_id→perros.id, medicamento TEXT, dosis TEXT, frecuencia TEXT, fecha_inicio DATE, fecha_fin DATE [NULL=en curso])

pesos_perro (id, perro_id→perros.id, fecha DATE, peso_kg FLOAT)

movimientos_economicos (id, tipo TEXT('ingreso'/'gasto'/'deuda'), concepto TEXT, categoria TEXT, importe FLOAT, fecha DATE, pagado BOOL)

eventos (id, titulo TEXT, fecha DATE, hora_inicio TEXT, hora_fin TEXT, ubicacion TEXT, tipo TEXT)
evento_voluntarios (id, evento_id→eventos.id, voluntario_id→voluntarios.id)

familias (id, nombre TEXT, apellidos TEXT, dni TEXT, tipo TEXT('adopcion'/'acogida'), perro_id→perros.id nullable, email TEXT, telefono TEXT, fecha_contrato DATE)

visitantes (id, nombre TEXT, apellido TEXT, email TEXT, telefono TEXT, fecha_contacto DATE, fecha_visita DATE, estado TEXT('interesado'/'visita_programada'/'visita_realizada'/'se_convirtio'/'descartado'))

periodos_apoyo (id, voluntario_id→voluntarios.id, fecha_inicio DATE, fecha_fin DATE [NULL=activo])
"""

_SYSTEM_SQL = f"""Eres un asistente de base de datos para la protectora de perros "Siempre Fiel".
Dado el esquema y una pregunta en español, genera ÚNICAMENTE una consulta SQL SELECT válida para PostgreSQL.

REGLAS ESTRICTAS:
- Solo SELECT. NUNCA uses DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, CREATE.
- Responde SOLO con la query SQL, sin explicación, sin markdown, sin comillas alrededor.
- Usa ILIKE para comparaciones de texto (case-insensitive).
- Los nombres de perros están en MAYÚSCULAS; usa UPPER() o ILIKE al comparar.
- En listados de perros muestra siempre el nombre (y raza si es relevante), nunca el id.
- Para calcular cuánto tiempo estuvo un perro en la protectora: usa COALESCE(fecha_adopcion, CURRENT_DATE) - fecha_entrada. Si ya fue adoptado, el período termina en fecha_adopcion, no hoy.
- Añade siempre LIMIT 50 salvo que el usuario pida un número concreto.
- Si la pregunta no puede responderse con los datos disponibles, responde exactamente: NO_PUEDO_RESPONDER

ESQUEMA:
{_SCHEMA}"""

_SYSTEM_ANSWER = """Eres AntonIA, el asistente inteligente de la protectora "Siempre Fiel".
Dado una pregunta y los resultados de una consulta a la base de datos, responde en español de forma natural, clara y amigable.

REGLAS:
- Resume los datos de forma comprensible para alguien no técnico.
- Si no hay resultados, dilo claramente y con empatía.
- Sé conciso pero informativo. Usa listas si hay varios elementos.
- No menciones SQL, tablas ni nada técnico.
- No inventes datos que no estén en los resultados."""

_DANGEROUS = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|EXEC|EXECUTE|GRANT|REVOKE|COPY|VACUUM)\b",
    re.IGNORECASE,
)


def _extraer_sql(texto: str) -> str:
    m = re.search(r"```(?:sql)?\s*([\s\S]+?)\s*```", texto, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return texto.strip()


def _validar_select(sql: str) -> bool:
    s = sql.strip()
    if not s.upper().startswith("SELECT"):
        return False
    if _DANGEROUS.search(s):
        return False
    return True


class Pregunta(BaseModel):
    pregunta: str


@router.get("/")
async def consulta_page(request: Request):
    return templates.TemplateResponse(request, "consulta/chat.html", {})


@router.post("/preguntar")
async def preguntar(body: Pregunta, db: Session = Depends(get_db)):
    pregunta = body.pregunta.strip()
    if not pregunta:
        return JSONResponse({"error": "Pregunta vacía."}, status_code=400)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return JSONResponse({"error": "GROQ_API_KEY no configurada en el servidor."}, status_code=500)

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        # Paso 1: generar SQL
        sql_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_SQL},
                {"role": "user", "content": pregunta},
            ],
            temperature=0,
            max_tokens=500,
        )
        sql_raw = sql_resp.choices[0].message.content.strip()

        if "NO_PUEDO_RESPONDER" in sql_raw.upper():
            return JSONResponse({"respuesta": "No tengo suficientes datos para responder esa pregunta con la información disponible."})

        sql = _extraer_sql(sql_raw)

        if not _validar_select(sql):
            logger.warning("SQL inseguro o inválido generado: %s", sql)
            return JSONResponse({"error": "No pude generar una consulta válida para esa pregunta."}, status_code=400)

        # Paso 2: ejecutar SQL
        try:
            result = db.execute(text(sql))
            rows = result.fetchall()
            columns = list(result.keys())
            datos = [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error("Error ejecutando SQL '%s': %s", sql, e)
            return JSONResponse({"error": "Error al consultar la base de datos. Intenta reformular la pregunta."}, status_code=500)

        # Paso 3: formatear respuesta en lenguaje natural
        datos_str = str(datos[:50]) if datos else "[]"
        answer_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_ANSWER},
                {"role": "user", "content": f"Pregunta: {pregunta}\n\nResultados de la base de datos: {datos_str}"},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        respuesta = answer_resp.choices[0].message.content.strip()
        return JSONResponse({"respuesta": respuesta})

    except Exception as e:
        logger.exception("Error en asistente IA: %s", e)
        return JSONResponse({"error": "Error interno del asistente. Inténtalo de nuevo."}, status_code=500)
