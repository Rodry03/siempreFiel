import os
import subprocess
from datetime import date
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.templates_config import templates
from app.auth import get_current_user, require_not_veterano, require_admin

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_not_veterano)])


def _query_analytics(db: Session, view: str) -> list[dict]:
    try:
        result = db.execute(text(f"SELECT * FROM analytics.{view}"))
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]
    except Exception:
        db.rollback()
        return []


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), dbt: str = ""):
    vacunas_proximas = _query_analytics(db, "mart_vacunas_proximas")
    no_esterilizados = _query_analytics(db, "mart_perros_no_esterilizados")
    tiempo_refugio = _query_analytics(db, "mart_tiempo_en_refugio")

    entradas_por_mes = _query_analytics(db, "mart_entradas_por_mes")
    entradas_salidas = _query_analytics(db, "mart_entradas_salidas_por_mes")

    from app.models import Perro, EstadoPerro, Voluntario, TipoUbicacion, Ubicacion
    from app.routers.turnos import calcular_saldo
    total_activos = db.query(Perro).filter(Perro.estado == EstadoPerro.activo).count()
    total_voluntarios = db.query(Voluntario).filter(Voluntario.activo == True).count()

    # Distribución de perros activos por ubicación actual (última ubicación de cada perro)
    perros_activos = db.query(Perro).filter(Perro.estado == EstadoPerro.activo).all()
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

    return templates.TemplateResponse(request, "dashboard.html", {
        "vacunas_proximas": vacunas_proximas,
        "no_esterilizados": no_esterilizados,
        "tiempo_refugio": tiempo_refugio,
        "total_activos": total_activos,
        "total_voluntarios": total_voluntarios,
        "voluntarios_top": voluntarios_top,
        "top_deudores": top_deudores,
        "entradas_por_mes": entradas_por_mes,
        "entradas_salidas": entradas_salidas,
        "dist_ubicacion": dist_ubicacion,
        "dbt_status": dbt,
    })


@router.post("/dbt-run", dependencies=[Depends(require_admin)])
def ejecutar_dbt():
    dbt_dir = os.path.join(os.getcwd(), "dbt_protectora")
    try:
        result = subprocess.run(
            ["dbt", "run"],
            cwd=dbt_dir,
            capture_output=True,
            timeout=180,
            env={**os.environ},
        )
        status = "ok" if result.returncode == 0 else "error"
    except Exception:
        status = "error"
    return RedirectResponse(f"/?dbt={status}", status_code=303)
