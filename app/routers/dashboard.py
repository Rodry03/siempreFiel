import asyncio
import logging
import os
import subprocess
import uuid
from datetime import date
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, extract, func
from app.database import get_db
from app.templates_config import templates
from app.auth import get_current_user, require_not_veterano, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_not_veterano)])

_dbt_jobs: dict[str, dict] = {}


def _dbt_subprocess(cmd: list[str], dbt_dir: str, env: dict, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=dbt_dir, capture_output=True, text=True, timeout=timeout, env=env)


async def _run_dbt_full(job_id: str):
    dbt_dir = os.path.join(os.getcwd(), "dbt_protectora")
    env = {**os.environ}
    try:
        deps = await asyncio.to_thread(_dbt_subprocess, ["dbt", "deps"], dbt_dir, env, 60)
        if deps.returncode != 0:
            output = (deps.stderr or deps.stdout or "").strip()
            logger.error("dbt deps FAILED:\n%s", output)
            _dbt_jobs[job_id] = {"status": "error", "output": f"Error en dbt deps:\n{output[-500:]}"}
            return

        result = await asyncio.to_thread(_dbt_subprocess, ["dbt", "run"], dbt_dir, env, 180)
        if result.returncode == 0:
            logger.info("dbt run OK")
            _dbt_jobs[job_id] = {"status": "ok", "output": "Analytics actualizados correctamente."}
        else:
            output = (result.stderr or result.stdout or "").strip()
            last_lines = "\n".join(output.splitlines()[-20:])
            logger.error("dbt run FAILED:\n%s", output)
            _dbt_jobs[job_id] = {"status": "error", "output": f"Error en dbt run:\n{last_lines}"}
    except subprocess.TimeoutExpired:
        _dbt_jobs[job_id] = {"status": "error", "output": "dbt superó el tiempo límite."}
    except Exception as e:
        logger.exception("dbt run excepción: %s", e)
        _dbt_jobs[job_id] = {"status": "error", "output": str(e)}


async def _run_dbt_model(job_id: str, model: str):
    dbt_dir = os.path.join(os.getcwd(), "dbt_protectora")
    env = {**os.environ}
    try:
        result = await asyncio.to_thread(
            _dbt_subprocess, ["dbt", "run", "--select", model], dbt_dir, env, 60
        )
        if result.returncode == 0:
            _dbt_jobs[job_id] = {"status": "ok", "output": f"{model} actualizado correctamente."}
        else:
            output = (result.stderr or result.stdout or "").strip()
            _dbt_jobs[job_id] = {"status": "error", "output": f"Error: {output[-300:]}"}
    except subprocess.TimeoutExpired:
        _dbt_jobs[job_id] = {"status": "error", "output": "dbt superó el tiempo límite."}
    except Exception as e:
        logger.exception("dbt run-model excepción: %s", e)
        _dbt_jobs[job_id] = {"status": "error", "output": str(e)}


_ALLOWED_VIEWS = {
    "mart_vacunas_proximas",
    "mart_perros_no_esterilizados",
    "mart_tiempo_en_refugio",
    "mart_entradas_salidas_por_mes",
    "mart_tiempo_adopcion",
    "mart_perros_sin_adoptar",
    "mart_patrones_dificultad",
    "mart_entradas_por_mes",
    "mart_saldo_turnos",
    "mart_tiempo_acogida_mes",
    "mart_conversion_visitantes",
    "mart_perros_urgentes_adopcion",
    "mart_cobertura_semanal",
    "mart_evolucion_saldo_semanal",
}


def _query_analytics(db: Session, view: str) -> list[dict]:
    from datetime import date as _date, datetime as _datetime
    if view not in _ALLOWED_VIEWS:
        raise ValueError(f"Vista no permitida: {view}")
    try:
        result = db.execute(text(f"SELECT * FROM analytics.{view}"))
        columns = result.keys()
        rows = []
        for row in result.fetchall():
            d = {}
            for k, v in zip(columns, row):
                d[k] = v.isoformat() if isinstance(v, (_date, _datetime)) else v
            rows.append(d)
        return rows
    except Exception:
        db.rollback()
        return []


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), dbt: str = ""):
    vacunas_proximas = _query_analytics(db, "mart_vacunas_proximas")
    no_esterilizados = _query_analytics(db, "mart_perros_no_esterilizados")

    entradas_salidas = [
        {**r, "mes": r["mes"].isoformat() if hasattr(r.get("mes"), "isoformat") else str(r.get("mes", ""))}
        for r in _query_analytics(db, "mart_entradas_salidas_por_mes")
    ]
    tiempo_adopcion = [
        {**r, "dias_medio": float(r["dias_medio"])}
        for r in _query_analytics(db, "mart_tiempo_adopcion")
    ]
    perros_sin_adoptar = _query_analytics(db, "mart_perros_sin_adoptar")
    perros_urgentes_adopcion = _query_analytics(db, "mart_perros_urgentes_adopcion")
    patrones_dificultad = _query_analytics(db, "mart_patrones_dificultad")
    tiempo_acogida = [
        {**r,
         "mes": r["mes"].isoformat() if hasattr(r.get("mes"), "isoformat") else str(r.get("mes", "")),
         "dias_medio": float(r["dias_medio"])}
        for r in _query_analytics(db, "mart_tiempo_acogida_mes")
    ]
    conversion_visitantes = [
        {**r,
         "mes": r["mes"].isoformat() if hasattr(r.get("mes"), "isoformat") else str(r.get("mes", "")),
         "tasa_conversion": float(r["tasa_conversion"]) if r.get("tasa_conversion") is not None else None}
        for r in _query_analytics(db, "mart_conversion_visitantes")
    ]
    from app.models import Perro, EstadoPerro, Voluntario, TipoUbicacion, Ubicacion
    from app.routers.turnos import calcular_saldo
    ESTADOS_ACTIVOS = [EstadoPerro.libre, EstadoPerro.reservado]
    total_activos = db.query(Perro).filter(Perro.estado.in_(ESTADOS_ACTIVOS)).count()
    total_voluntarios = db.query(Voluntario).filter(Voluntario.activo == True).count()

    # Distribución de perros activos por ubicación actual (última ubicación de cada perro)
    perros_activos = db.query(Perro).filter(Perro.estado.in_(ESTADOS_ACTIVOS)).all()
    dist_ubicacion = {"refugio": 0, "acogida": 0, "residencia": 0, "sin_ubicacion": 0}
    for perro in perros_activos:
        if perro.ubicaciones:
            tipo = perro.ubicaciones[0].tipo.value
            if tipo in dist_ubicacion:
                dist_ubicacion[tipo] += 1
            else:
                dist_ubicacion["sin_ubicacion"] += 1
        else:
            dist_ubicacion["sin_ubicacion"] += 1

    hoy = date.today()
    voluntarios_top = [
        {"voluntario": v, "dias": (hoy - v.fecha_alta).days}
        for v in db.query(Voluntario)
            .filter(Voluntario.activo == True)
            .order_by(Voluntario.fecha_alta.asc())
            .limit(10)
            .all()
    ]

    from app.routers.turnos import PERFILES_SIN_TURNOS
    top_deudores = sorted(
        [{"voluntario": v, "saldo": calcular_saldo(v)}
         for v in db.query(Voluntario)
             .filter(Voluntario.activo == True, Voluntario.perfil.notin_(PERFILES_SIN_TURNOS))
             .all()
         if calcular_saldo(v) < 0],
        key=lambda x: x["saldo"]
    )[:10]

    cobertura_raw = _query_analytics(db, "mart_cobertura_semanal")
    cobertura_mensual = [
        {
            "semana_label": r["semana_label"],
            "slots_con_veterano": r["slots_con_veterano"],
            "slots_sin_cubrir": r["slots_sin_cubrir"],
            "nivel": r["nivel"],
            "pct_con_veterano": float(r["pct_con_veterano"]) if r.get("pct_con_veterano") is not None else 0.0,
        }
        for r in reversed(cobertura_raw)
    ]

    evolucion_raw = _query_analytics(db, "mart_evolucion_saldo_semanal")
    evolucion_saldo_mensual = [
        {
            "semana_label": r["semana_label"],
            "saldo_medio": float(r["saldo_medio"]) if r.get("saldo_medio") is not None else 0.0,
            "n_voluntarios": r["n_voluntarios"],
            "n_con_deuda": r["n_con_deuda"],
        }
        for r in evolucion_raw
    ]

    return templates.TemplateResponse(request, "dashboard.html", {
        "vacunas_proximas": vacunas_proximas,
        "no_esterilizados": no_esterilizados,
        "total_activos": total_activos,
        "total_voluntarios": total_voluntarios,
        "voluntarios_top": voluntarios_top,
        "top_deudores": top_deudores,
        "entradas_salidas": entradas_salidas,
        "tiempo_adopcion": tiempo_adopcion,
        "perros_sin_adoptar": perros_sin_adoptar,
        "perros_urgentes_adopcion": perros_urgentes_adopcion,
        "patrones_dificultad": patrones_dificultad,
        "cobertura_mensual": cobertura_mensual,
        "tiempo_acogida": tiempo_acogida,
        "conversion_visitantes": conversion_visitantes,
        "evolucion_saldo_mensual": evolucion_saldo_mensual,
        "dist_ubicacion": dist_ubicacion,
        "dbt_status": dbt,
    })


@router.get("/dashboard/detalle-mes")
def detalle_mes(
    mes: str = Query(...),
    tipo: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.models import Perro, Raza
    try:
        mes_date = date.fromisoformat(mes)
    except ValueError:
        return JSONResponse({"error": "mes inválido"}, status_code=400)

    if tipo == "entradas":
        perros = (
            db.query(Perro)
            .join(Raza, Perro.raza_id == Raza.id)
            .filter(
                extract("year", Perro.fecha_entrada) == mes_date.year,
                extract("month", Perro.fecha_entrada) == mes_date.month,
            )
            .order_by(Perro.fecha_entrada.desc())
            .all()
        )
        items = [
            {
                "id": p.id,
                "nombre": p.nombre,
                "raza": p.raza.nombre if p.raza else "—",
                "sexo": p.sexo.value,
                "fecha": p.fecha_entrada.isoformat(),
                "estado": p.estado.value,
            }
            for p in perros
        ]
    elif tipo == "adopciones":
        from sqlalchemy import desc
        perros = (
            db.query(Perro)
            .join(Raza, Perro.raza_id == Raza.id)
            .filter(
                Perro.fecha_adopcion.isnot(None),
                extract("year", Perro.fecha_adopcion) == mes_date.year,
                extract("month", Perro.fecha_adopcion) == mes_date.month,
            )
            .order_by(desc(Perro.fecha_adopcion))
            .all()
        )
        items = [
            {
                "id": p.id,
                "nombre": p.nombre,
                "raza": p.raza.nombre if p.raza else "—",
                "sexo": p.sexo.value,
                "fecha": p.fecha_adopcion.isoformat(),
                "estado": p.estado.value,
            }
            for p in perros
        ]
    else:
        return JSONResponse({"error": "tipo inválido"}, status_code=400)

    return JSONResponse({"items": items})


@router.get("/dashboard/detalle-conversion")
def detalle_conversion(
    mes: str = Query(...),
    tipo: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.models import Visitante, EstadoVisitante
    try:
        mes_date = date.fromisoformat(mes)
    except ValueError:
        return JSONResponse({"error": "mes inválido"}, status_code=400)

    query = db.query(Visitante).filter(
        extract("year", Visitante.fecha_contacto) == mes_date.year,
        extract("month", Visitante.fecha_contacto) == mes_date.month,
    )
    if tipo == "convertidos":
        query = query.filter(Visitante.estado == EstadoVisitante.se_convirtio)
    elif tipo != "todos":
        return JSONResponse({"error": "tipo inválido"}, status_code=400)

    visitantes = query.order_by(Visitante.fecha_contacto.desc()).all()
    items = [
        {
            "id": v.id,
            "nombre": f"{v.nombre} {v.apellido}",
            "email": v.email or "—",
            "telefono": v.telefono or "—",
            "fecha": v.fecha_contacto.isoformat(),
            "estado": v.estado.value,
        }
        for v in visitantes
    ]
    return JSONResponse({"items": items})


@router.get("/dashboard/detalle-perros-activos")
def detalle_perros_activos(db: Session = Depends(get_db)):
    from app.models import Perro, EstadoPerro
    ESTADOS_ACTIVOS = [EstadoPerro.libre, EstadoPerro.reservado]
    perros = db.query(Perro).filter(Perro.estado.in_(ESTADOS_ACTIVOS)).order_by(Perro.nombre).all()
    items = []
    for p in perros:
        ub = p.ubicaciones[0].tipo.value.replace("_", " ") if p.ubicaciones else "—"
        items.append({
            "id": p.id,
            "nombre": p.nombre,
            "raza": p.raza.nombre if p.raza else "—",
            "sexo": p.sexo.value,
            "estado": p.estado.value,
            "ubicacion": ub,
        })
    return JSONResponse({"items": items})


@router.get("/dashboard/detalle-refugio")
def detalle_refugio(db: Session = Depends(get_db)):
    from app.models import Perro, EstadoPerro, TipoUbicacion
    ESTADOS_ACTIVOS = [EstadoPerro.libre, EstadoPerro.reservado]
    perros = db.query(Perro).filter(Perro.estado.in_(ESTADOS_ACTIVOS)).order_by(Perro.nombre).all()
    items = []
    for p in perros:
        if p.ubicaciones and p.ubicaciones[0].tipo == TipoUbicacion.refugio:
            items.append({
                "id": p.id,
                "nombre": p.nombre,
                "raza": p.raza.nombre if p.raza else "—",
                "sexo": p.sexo.value,
                "estado": p.estado.value,
                "fecha_entrada": p.fecha_entrada.isoformat() if p.fecha_entrada else "—",
            })
    return JSONResponse({"items": items})


@router.get("/dashboard/detalle-voluntarios")
def detalle_voluntarios_activos(db: Session = Depends(get_db)):
    from app.models import Voluntario
    voluntarios = db.query(Voluntario).filter(Voluntario.activo == True).order_by(Voluntario.nombre).all()
    items = [
        {
            "id": v.id,
            "nombre": f"{v.nombre} {v.apellido}",
            "perfil": v.perfil.value,
            "fecha_alta": v.fecha_alta.isoformat() if v.fecha_alta else "—",
            "email": v.email or "—",
            "telefono": v.telefono or "—",
        }
        for v in voluntarios
    ]
    return JSONResponse({"items": items})


@router.post("/dbt-run", dependencies=[Depends(require_admin)])
async def ejecutar_dbt(request: Request):
    job_id = str(uuid.uuid4())[:8]
    _dbt_jobs[job_id] = {"status": "running", "output": ""}
    asyncio.create_task(_run_dbt_full(job_id))
    return JSONResponse({"job_id": job_id})


@router.get("/dbt-status/{job_id}", dependencies=[Depends(require_admin)])
def dbt_status(job_id: str):
    job = _dbt_jobs.get(job_id)
    if not job:
        return JSONResponse({"status": "unknown"}, status_code=404)
    return JSONResponse(job)


_ALLOWED_MODELS = {
    "mart_cobertura_semanal",
    "mart_saldo_turnos_semanal",
    "mart_evolucion_saldo_semanal",
}


@router.post("/dbt-run-model", dependencies=[Depends(require_admin)])
async def ejecutar_dbt_model(request: Request):
    form = await request.form()
    model = form.get("model", "")
    if model not in _ALLOWED_MODELS:
        return JSONResponse({"status": "error", "output": "Modelo no permitido."})
    job_id = str(uuid.uuid4())[:8]
    _dbt_jobs[job_id] = {"status": "running", "output": ""}
    asyncio.create_task(_run_dbt_model(job_id, model))
    return JSONResponse({"job_id": job_id})
