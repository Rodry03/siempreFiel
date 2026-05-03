import os
import subprocess
from datetime import date
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, extract
from app.database import get_db
from app.templates_config import templates
from app.auth import get_current_user, require_not_veterano, require_admin

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_not_veterano)])


_ALLOWED_VIEWS = {
    "mart_vacunas_proximas",
    "mart_perros_no_esterilizados",
    "mart_tiempo_en_refugio",
    "mart_entradas_salidas_por_mes",
    "mart_tiempo_adopcion",
    "mart_perros_sin_adoptar",
    "mart_patrones_dificultad",
    "mart_cobertura_semanal",
    "mart_faltas_voluntario",
    "mart_entradas_por_mes",
    "mart_saldo_turnos",
    "mart_saldo_turnos_semanal",
    "mart_tiempo_acogida_mes",
    "mart_conversion_visitantes",
    "mart_evolucion_saldo_semanal",
}


def _query_analytics(db: Session, view: str) -> list[dict]:
    if view not in _ALLOWED_VIEWS:
        raise ValueError(f"Vista no permitida: {view}")
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

    entradas_salidas = [
        {**r, "mes": r["mes"].isoformat() if hasattr(r.get("mes"), "isoformat") else str(r.get("mes", ""))}
        for r in _query_analytics(db, "mart_entradas_salidas_por_mes")
    ]
    tiempo_adopcion = [
        {**r, "dias_medio": float(r["dias_medio"])}
        for r in _query_analytics(db, "mart_tiempo_adopcion")
    ]
    perros_sin_adoptar = _query_analytics(db, "mart_perros_sin_adoptar")
    patrones_dificultad = _query_analytics(db, "mart_patrones_dificultad")
    cobertura_semanal = [
        {**r,
         "pct_con_veterano": float(r["pct_con_veterano"]),
         "pct_completos":    float(r["pct_completos"])}
        for r in _query_analytics(db, "mart_cobertura_semanal")
    ]
    faltas_voluntario = _query_analytics(db, "mart_faltas_voluntario")
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
    evolucion_saldo = [
        {**r,
         "semana": r["semana"].isoformat() if hasattr(r.get("semana"), "isoformat") else str(r.get("semana", "")),
         "saldo_medio": float(r["saldo_medio"]) if r.get("saldo_medio") is not None else 0.0}
        for r in _query_analytics(db, "mart_evolucion_saldo_semanal")
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

    return templates.TemplateResponse(request, "dashboard.html", {
        "vacunas_proximas": vacunas_proximas,
        "no_esterilizados": no_esterilizados,
        "tiempo_refugio": tiempo_refugio,
        "total_activos": total_activos,
        "total_voluntarios": total_voluntarios,
        "voluntarios_top": voluntarios_top,
        "top_deudores": top_deudores,
        "entradas_salidas": entradas_salidas,
        "tiempo_adopcion": tiempo_adopcion,
        "perros_sin_adoptar": perros_sin_adoptar,
        "patrones_dificultad": patrones_dificultad,
        "cobertura_semanal": cobertura_semanal,
        "faltas_voluntario": faltas_voluntario,
        "tiempo_acogida": tiempo_acogida,
        "conversion_visitantes": conversion_visitantes,
        "evolucion_saldo": evolucion_saldo,
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
