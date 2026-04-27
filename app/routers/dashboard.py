from datetime import date
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.templates_config import templates
from app.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


def _query_analytics(db: Session, view: str) -> list[dict]:
    try:
        result = db.execute(text(f"SELECT * FROM analytics.{view}"))
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]
    except Exception:
        db.rollback()
        return []


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    vacunas_proximas = _query_analytics(db, "mart_vacunas_proximas")
    no_esterilizados = _query_analytics(db, "mart_perros_no_esterilizados")
    tiempo_refugio = _query_analytics(db, "mart_tiempo_en_refugio")

    from app.models import Perro, EstadoPerro, Voluntario
    from app.routers.turnos import calcular_saldo
    total_activos = db.query(Perro).filter(Perro.estado == EstadoPerro.activo).count()

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
        "voluntarios_top": voluntarios_top,
        "top_deudores": top_deudores,
    })
