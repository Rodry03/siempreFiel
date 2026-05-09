import logging
import os
import subprocess
from datetime import date
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, extract, func
from calendar import monthrange
from app.database import get_db
from app.templates_config import templates
from app.auth import get_current_user, require_not_veterano, require_admin, flash

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user), Depends(require_not_veterano)])


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
    from app.models import Perro, EstadoPerro, Voluntario, TipoUbicacion, Ubicacion, TurnoMensual
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

    from app.routers.turnos import PERFILES_SIN_TURNOS, MESES_ES
    top_deudores = sorted(
        [{"voluntario": v, "saldo": calcular_saldo(v)}
         for v in db.query(Voluntario)
             .filter(Voluntario.activo == True, Voluntario.perfil.notin_(PERFILES_SIN_TURNOS))
             .all()
         if calcular_saldo(v) < 0],
        key=lambda x: x["saldo"]
    )[:10]

    from app.models import SaldoMensual
    saldo_historico = db.query(SaldoMensual).order_by(SaldoMensual.mes).all()
    saldos_por_mes = {}
    for s in saldo_historico:
        saldos_por_mes.setdefault(s.mes, []).append(s.saldo)
    evolucion_saldo_mensual = [
        {
            "mes_label": f"{MESES_ES[m.month]} {m.year}",
            "deuda_total": round(sum(abs(s) for s in saldos if s < 0), 1),
            "n_con_deuda": sum(1 for s in saldos if s < 0),
        }
        for m, saldos in sorted(saldos_por_mes.items())
    ]
    voluntarios_con_turnos = (
        db.query(Voluntario)
        .filter(Voluntario.activo == True, Voluntario.perfil.notin_(list(PERFILES_SIN_TURNOS)))
        .all()
    )
    all_tm = db.query(TurnoMensual).filter(
        TurnoMensual.voluntario_id.in_([v.id for v in voluntarios_con_turnos])
    ).all()
    tm_by_vol = {}
    for t in all_tm:
        tm_by_vol.setdefault(t.voluntario_id, []).append(t)

    meses_list = sorted(set(t.mes for t in all_tm))

    cobertura_mensual = []
    for mes_date in meses_list:
        total_realizados = sum(t.turnos for t in all_tm if t.mes == mes_date)
        dias_mes = monthrange(mes_date.year, mes_date.month)[1]
        esperados = dias_mes * 2
        porcentaje = round(total_realizados / esperados * 100, 1)
        cobertura_mensual.append({
            "mes_label": f"{MESES_ES[mes_date.month]} {mes_date.year}",
            "total_realizados": total_realizados,
            "esperados": esperados,
            "sin_cubrir": max(0, esperados - total_realizados),
            "porcentaje": porcentaje,
        })

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
def ejecutar_dbt(request: Request):
    dbt_dir = os.path.join(os.getcwd(), "dbt_protectora")
    env = {**os.environ}
    try:
        deps = subprocess.run(
            ["dbt", "deps"],
            cwd=dbt_dir,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if deps.returncode != 0:
            output = (deps.stderr or deps.stdout or "Sin salida").strip()
            logger.error("dbt deps FAILED:\n%s", output)
            flash(request, f"Error al instalar dependencias dbt:\n{output[-500:]}", "danger")
            return RedirectResponse("/", status_code=303)

        result = subprocess.run(
            ["dbt", "run"],
            cwd=dbt_dir,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        if result.returncode == 0:
            logger.info("dbt run OK:\n%s", result.stdout)
            flash(request, "Analytics actualizados correctamente.", "success")
        else:
            output = (result.stderr or result.stdout or "Sin salida").strip()
            last_lines = "\n".join(output.splitlines()[-20:])
            logger.error("dbt run FAILED (code %d):\n%s", result.returncode, output)
            flash(request, f"Error al ejecutar dbt run:\n{last_lines}", "danger")
    except subprocess.TimeoutExpired:
        logger.error("dbt run timeout")
        flash(request, "dbt run superó el tiempo límite.", "danger")
    except Exception as e:
        logger.exception("dbt run excepción: %s", e)
        flash(request, f"Error inesperado al ejecutar dbt: {e}", "danger")
    return RedirectResponse("/", status_code=303)
