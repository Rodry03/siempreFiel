import os
import re
import json
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
  NOTA: estado='libre' o 'reservado' = bajo gestión de la protectora (NO indica dónde están físicamente).
  Para saber cuántos perros hay en un lugar físico usa SIEMPRE la tabla ubicaciones.

razas (id, nombre TEXT)

ubicaciones (id, perro_id→perros.id, tipo TEXT('refugio'/'acogida'/'residencia'/'casa_adoptiva'), fecha_inicio DATE, fecha_fin DATE [NULL=ubicación ACTUAL/activa], nombre_contacto TEXT, telefono_contacto TEXT)
  NOTA: la ubicación actual de un perro es la fila con fecha_fin IS NULL.
  "perros en el refugio" = JOIN ubicaciones WHERE tipo='refugio' AND fecha_fin IS NULL
  "perros en acogida"   = JOIN ubicaciones WHERE tipo='acogida'  AND fecha_fin IS NULL

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

-- Vista precalculada de saldo de turnos (schema analytics):
analytics.mart_saldo_turnos_semanal (voluntario_id, nombre TEXT, apellido TEXT, perfil TEXT, semana DATE, turnos_semana FLOAT, saldo_semana FLOAT, saldo_acumulado FLOAT)
  saldo_acumulado: saldo total acumulado hasta esa semana. Negativo = debe turnos. Positivo = turnos de sobra.
  Para el saldo ACTUAL de cada voluntario: filtra por la semana más reciente anterior a la semana en curso:
    WHERE semana = (SELECT MAX(semana) FROM analytics.mart_saldo_turnos_semanal WHERE semana < date_trunc('week', current_date)::date)
  Usa SIEMPRE esta tabla para preguntas sobre saldo, deuda de turnos o voluntarios al día.
"""

_SYSTEM_SQL = f"""Eres el asistente de base de datos de la protectora de perros "Siempre Fiel".
Tienes disponibles DOS herramientas:

- buscar_perro_por_nombre: úsala SOLO cuando la pregunta sea sobre UN perro concreto
  identificado por su nombre (su estado, raza o ubicación actual). Es más rápida y
  segura que generar SQL para este caso, úsala siempre que aplique.
- ejecutar_consulta_sql: úsala para cualquier otra pregunta (listados, conteos, filtros,
  agregaciones, turnos, economía, vacunas, etc.), generando tú mismo el SQL.

Si decides usar ejecutar_consulta_sql, sigue estas reglas para el SQL que generes:

REGLAS ESTRICTAS:
- Solo SELECT. NUNCA uses DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, CREATE.
- Usa ILIKE para comparaciones de texto libre (nombres, notas, etc.).
- Las columnas de tipo enum (estado, perfil, franja, sexo, tipo en ubicaciones/movimientos/visitantes) son enums de PostgreSQL: usa siempre `= 'valor'` (NO ILIKE ni LIKE), o `::text = 'valor'` si necesitas cast.
- Los nombres de perros están en MAYÚSCULAS; usa UPPER() o ILIKE al comparar.
- En listados de perros muestra siempre el nombre (y raza si es relevante), nunca el id.
- Para calcular cuánto tiempo estuvo un perro en la protectora: usa COALESCE(fecha_adopcion, CURRENT_DATE) - fecha_entrada. Si ya fue adoptado, el período termina en fecha_adopcion, no hoy.
- "perros en el refugio/acogida/residencia" → filtra por ubicaciones.tipo y fecha_fin IS NULL. NUNCA uses perros.estado para responder preguntas sobre ubicación física.
- Añade siempre LIMIT 50 salvo que el usuario pida un número concreto.

Si la pregunta no puede responderse con los datos disponibles, NO uses ninguna herramienta:
responde directamente en texto explicando que no tienes esos datos.

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
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|EXEC|EXECUTE|GRANT|REVOKE|COPY|VACUUM"
    r"|pg_read_file|pg_read_binary_file|pg_ls_dir|pg_stat_file|lo_export|lo_import|lo_create|lo_unlink"
    r"|pg_sleep|pg_cancel_backend|pg_terminate_backend|dblink|dblink_exec"
    r"|PERFORM|DO\s+\$\$|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b",
    re.IGNORECASE,
)

MAX_INTENTOS_SQL = 3  # límite para evitar bucles infinitos si el modelo no logra corregir el SQL


_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "buscar_perro_por_nombre",
            "description": (
                "Busca un perro por su nombre (exacto o parcial) y devuelve sus datos "
                "básicos: raza, estado y ubicación actual. Úsala SOLO para preguntas "
                "sobre un perro concreto identificado por nombre."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre del perro a buscar"}
                },
                "required": ["nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ejecutar_consulta_sql",
            "description": (
                "Ejecuta una consulta SQL SELECT sobre la base de datos de la protectora. "
                "Úsala para listados, conteos, filtros, agregaciones, turnos, economía, "
                "vacunas y cualquier pregunta que no sea una búsqueda simple por nombre."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "La consulta SQL SELECT completa para PostgreSQL"}
                },
                "required": ["sql"],
            },
        },
    },
]


def _buscar_perro_por_nombre(db: Session, nombre: str) -> dict:
    """Consulta directa y parametrizada -- no hay SQL generado por el modelo aquí,
    así que no hace falta reintento: o encuentra filas, o no las encuentra, pero
    nunca puede romperse por una columna mal escrita o un JOIN incorrecto."""
    nombre = (nombre or "").strip()
    if not nombre:
        return {"error": "No se indicó ningún nombre de perro."}

    sql = text("""
        SELECT p.nombre, p.fecha_nacimiento, p.estado, r.nombre AS raza, u.tipo AS ubicacion_actual
        FROM perros p
        LEFT JOIN razas r ON r.id = p.raza_id
        LEFT JOIN ubicaciones u ON u.perro_id = p.id AND u.fecha_fin IS NULL
        WHERE p.nombre ILIKE :patron
        LIMIT 5
    """)
    rows = db.execute(sql, {"patron": f"%{nombre}%"}).fetchall()

    if not rows:
        return {"error": f"No encontré ningún perro llamado '{nombre}'."}

    columnas = ["nombre", "fecha_nacimiento", "estado", "raza", "ubicacion_actual"]
    return {"perros": [dict(zip(columnas, row)) for row in rows]}


def _validar_select(sql: str) -> bool:
    s = sql.strip()
    if not s.upper().startswith("SELECT"):
        return False
    if _DANGEROUS.search(s):
        return False
    return True


class MensajeHistorial(BaseModel):
    role: str
    content: str


class Pregunta(BaseModel):
    pregunta: str
    history: list[MensajeHistorial] = []


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

        # Decisión + ejecución: el modelo elige qué herramienta usar, con reintento
        # si ejecutar_consulta_sql falla (mismo patrón del Bloque 2/4, ahora con el
        # protocolo de tool calling real -- role:"tool", no un mensaje de usuario fingido).
        messages = [{"role": "system", "content": _SYSTEM_SQL}]
        for h in body.history[-12:]:  # máx 6 intercambios anteriores
            if h.role in ("user", "assistant"):
                messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": pregunta})

        sql = None
        datos = None

        for intento in range(MAX_INTENTOS_SQL):
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                tools=_TOOLS_SCHEMA,
                temperature=0,
                max_tokens=500,
            )
            msg = resp.choices[0].message

            if not msg.tool_calls:
                # No usó ninguna herramienta -- normalmente porque decidió que no
                # puede responder con los datos disponibles. Se lo pasamos al usuario tal cual.
                return JSONResponse({"respuesta": msg.content, "sql": None})

            messages.append(msg)
            hubo_error_este_turno = False

            # Puede pedir varias herramientas en el mismo turno (Bloque 2/3): hay que
            # responder a TODAS con un mensaje "tool", o la siguiente llamada falla.
            for tool_call in msg.tool_calls:
                nombre_funcion = tool_call.function.name
                try:
                    argumentos = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    argumentos = {}

                if nombre_funcion == "buscar_perro_por_nombre":
                    resultado = _buscar_perro_por_nombre(db, argumentos.get("nombre", ""))
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(resultado, default=str)})
                    datos = resultado
                    sql = f"-- buscar_perro_por_nombre(nombre='{argumentos.get('nombre', '')}')"

                elif nombre_funcion == "ejecutar_consulta_sql":
                    sql_candidato = argumentos.get("sql", "")

                    if not _validar_select(sql_candidato):
                        logger.warning("Intento %d: SQL inseguro o inválido: %s", intento, sql_candidato)
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": (
                            "Esa consulta no es válida: debe ser un único SELECT, sin instrucciones peligrosas. "
                            "Genera de nuevo SOLO la consulta SQL corregida."
                        )})
                        hubo_error_este_turno = True
                        continue

                    try:
                        result = db.execute(text(sql_candidato))
                        rows = result.fetchall()
                        columns = list(result.keys())
                        datos = [dict(zip(columns, row)) for row in rows]
                        sql = sql_candidato
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": f"OK, {len(datos)} fila(s) devueltas."})
                        logger.warning("SQL correcto en el intento %d (de %d posibles)", intento, MAX_INTENTOS_SQL)
                    except Exception as e:
                        # Ver Bloque 6 anterior: el rollback es imprescindible, sin él
                        # el siguiente intento fallaría también con un error distinto.
                        db.rollback()
                        logger.warning("Intento %d: error ejecutando SQL '%s': %s", intento, sql_candidato, e)
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": (
                            f"Esa consulta falló al ejecutarse en PostgreSQL con este error real:\n{e}\n"
                            "Genera de nuevo SOLO la consulta SQL corregida, teniendo en cuenta el error."
                        )})
                        hubo_error_este_turno = True

                else:
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": f"Herramienta desconocida: {nombre_funcion}"})
                    hubo_error_este_turno = True

            if not hubo_error_este_turno:
                break  # todas las herramientas de este turno tuvieron éxito

        if datos is None:
            # Se acabaron los intentos: nos rendimos con elegancia (Bloque 1, punto 4d).
            return JSONResponse({"error": "No pude generar una consulta válida para esa pregunta tras varios intentos. Intenta reformularla."}, status_code=500)

        # Paso 3: formatear respuesta en lenguaje natural
        if isinstance(datos, list):
            datos_str = str(datos[:50]) if datos else "[]"
        else:
            datos_str = str(datos) if datos else "[]"
        messages_answer = [{"role": "system", "content": _SYSTEM_ANSWER}]
        # OJO: el historial guarda el SQL real en los turnos "assistant" (correcto
        # para el Paso 1, que sí necesita precisión técnica). Aquí solo queremos las
        # preguntas anteriores del usuario, en lenguaje natural -- nunca el SQL,
        # porque _SYSTEM_ANSWER tiene prohibido explícitamente mencionar nada técnico.
        for h in body.history[-4:]:
            if h.role == "user":
                messages_answer.append({"role": "user", "content": h.content})
        messages_answer.append({"role": "user", "content": f"Pregunta: {pregunta}\n\nResultados de la base de datos: {datos_str}"})

        answer_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages_answer,
            temperature=0.3,
            max_tokens=400,
        )
        respuesta = answer_resp.choices[0].message.content.strip()
        return JSONResponse({"respuesta": respuesta, "sql": sql})

    except Exception as e:
        logger.exception("Error en asistente IA: %s", e)
        return JSONResponse({"error": "Error interno del asistente. Inténtalo de nuevo."}, status_code=500)