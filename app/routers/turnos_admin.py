from datetime import date
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.auth import get_current_user, require_not_veterano, flash
from app.database import get_db
from app.models import TurnoMensual, Voluntario
from app.routers.turnos import PERFIL_LABELS, PERFIL_COLORS, PERFILES_SIN_TURNOS, MESES_ES, calcular_saldo
from app.templates_config import templates

router = APIRouter(
    prefix="/turnos",
    dependencies=[Depends(get_current_user), Depends(require_not_veterano)],
)


def _mes_anterior(mes: date) -> date:
    if mes.month == 1:
        return date(mes.year - 1, 12, 1)
    return date(mes.year, mes.month - 1, 1)


def _mes_siguiente(mes: date) -> date:
    if mes.month == 12:
        return date(mes.year + 1, 1, 1)
    return date(mes.year, mes.month + 1, 1)


@router.get("/")
def listar_turnos(
    request: Request,
    mes: Optional[str] = None,
    db: Session = Depends(get_db),
):
    hoy = date.today()
    if mes:
        try:
            mes_date = date.fromisoformat(mes + "-01")
        except ValueError:
            mes_date = _mes_anterior(date(hoy.year, hoy.month, 1))
    else:
        mes_date = _mes_anterior(date(hoy.year, hoy.month, 1))

    voluntarios = (
        db.query(Voluntario)
        .filter(Voluntario.activo == True, Voluntario.perfil.notin_(list(PERFILES_SIN_TURNOS)))
        .order_by(Voluntario.apellido, Voluntario.nombre)
        .all()
    )

    turnos_mes = {
        t.voluntario_id: t
        for t in db.query(TurnoMensual).filter(TurnoMensual.mes == mes_date).all()
    }

    voluntarios_data = [
        {"voluntario": v, "saldo": calcular_saldo(v)}
        for v in voluntarios
    ]

    return templates.TemplateResponse(request, "turnos/list.html", {
        "mes": mes_date,
        "mes_label": f"{MESES_ES[mes_date.month]} {mes_date.year}",
        "mes_anterior": _mes_anterior(mes_date).strftime("%Y-%m"),
        "mes_siguiente": _mes_siguiente(mes_date).strftime("%Y-%m"),
        "voluntarios_data": voluntarios_data,
        "turnos_mes": turnos_mes,
        "perfil_labels": PERFIL_LABELS,
        "perfil_colors": PERFIL_COLORS,
    })


@router.post("/guardar")
async def guardar_turnos_mes(
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    mes_str = form.get("mes")
    try:
        mes_date = date.fromisoformat(mes_str)
    except (ValueError, TypeError):
        flash(request, "Mes inválido.", "danger")
        return RedirectResponse("/turnos/", status_code=303)

    for key, value in form.multi_items():
        if not key.startswith("turnos_"):
            continue
        try:
            voluntario_id = int(key[len("turnos_"):])
            turnos_val = float(value) if value else 0.0
        except (ValueError, IndexError):
            continue

        existing = db.query(TurnoMensual).filter(
            TurnoMensual.voluntario_id == voluntario_id,
            TurnoMensual.mes == mes_date,
        ).first()

        if existing:
            existing.turnos = turnos_val
        else:
            db.add(TurnoMensual(
                voluntario_id=voluntario_id,
                mes=mes_date,
                turnos=turnos_val,
            ))

    db.commit()
    flash(request, f"Turnos de {MESES_ES[mes_date.month]} {mes_date.year} guardados.")
    return RedirectResponse(f"/turnos/?mes={mes_date.strftime('%Y-%m')}", status_code=303)
