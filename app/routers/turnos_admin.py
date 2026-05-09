from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.auth import get_current_user, require_admin, flash
from app.database import get_db
from app.models import TurnoVoluntario, EstadoTurno, Voluntario, PerfilVoluntario
from app.routers.turnos import (
    PERFIL_LABELS, PERFIL_COLORS, PERFILES_SIN_TURNOS,
    DIAS_ES, FRANJA_LABELS, calcular_saldo,
)
from app.templates_config import templates

router = APIRouter(
    prefix="/turnos",
    dependencies=[Depends(get_current_user), Depends(require_admin)],
)


def _semana_lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


@router.get("/")
def listar_turnos(
    request: Request,
    semana: Optional[str] = None,
    perfil: Optional[str] = None,
    db: Session = Depends(get_db),
):
    hoy = date.today()
    if semana:
        try:
            semana_date = _semana_lunes(date.fromisoformat(semana))
        except ValueError:
            semana_date = _semana_lunes(hoy)
    else:
        semana_date = _semana_lunes(hoy)

    semana_fin = semana_date + timedelta(days=6)

    q = (
        db.query(Voluntario)
        .filter(Voluntario.activo == True, Voluntario.perfil.notin_(list(PERFILES_SIN_TURNOS)))
    )
    if perfil:
        try:
            q = q.filter(Voluntario.perfil == PerfilVoluntario(perfil))
        except ValueError:
            perfil = None
    voluntarios = q.order_by(Voluntario.nombre, Voluntario.apellido).all()

    turnos_semana = (
        db.query(TurnoVoluntario)
        .filter(TurnoVoluntario.fecha >= semana_date, TurnoVoluntario.fecha <= semana_fin)
        .all()
    )

    turnos_por_vol = {}
    for t in turnos_semana:
        turnos_por_vol.setdefault(t.voluntario_id, []).append(t)
    for v_id in turnos_por_vol:
        turnos_por_vol[v_id].sort(key=lambda t: (t.fecha, t.franja.value))

    def _valor(t):
        return 0.5 if t.estado == EstadoTurno.medio_turno else 1.0

    def _en_apoyo(v):
        return any(
            p.fecha_inicio <= semana_fin and (p.fecha_fin is None or p.fecha_fin >= semana_date)
            for p in v.periodos_apoyo
        )

    voluntarios_data = [
        {
            "voluntario": v,
            "saldo": calcular_saldo(v),
            "turnos": turnos_por_vol.get(v.id, []),
            "total_valor": sum(_valor(t) for t in turnos_por_vol.get(v.id, [])),
            "en_apoyo": _en_apoyo(v),
        }
        for v in voluntarios
    ]

    dias = [semana_date + timedelta(days=i) for i in range(7)]
    perfiles_con_turnos = [p.value for p in PerfilVoluntario if p not in PERFILES_SIN_TURNOS]

    return templates.TemplateResponse(request, "turnos/list.html", {
        "semana": semana_date,
        "semana_fin": semana_fin,
        "semana_label": f"{semana_date.strftime('%d/%m')} – {semana_fin.strftime('%d/%m/%Y')}",
        "semana_anterior": (semana_date - timedelta(days=7)).isoformat(),
        "semana_siguiente": (semana_date + timedelta(days=7)).isoformat(),
        "dias": dias,
        "voluntarios_data": voluntarios_data,
        "perfil_labels": PERFIL_LABELS,
        "perfil_colors": PERFIL_COLORS,
        "dias_labels": DIAS_ES,
        "franja_labels": FRANJA_LABELS,
        "perfil_filtro": perfil or "",
        "perfiles_con_turnos": perfiles_con_turnos,
    })


@router.post("/anadir")
async def anadir_turno(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    semana_str = form.get("semana", "")
    perfil_str = form.get("perfil_filtro", "")
    perfil_qs = f"&perfil={perfil_str}" if perfil_str else ""
    try:
        voluntario_id = int(form.get("voluntario_id"))
        fecha = date.fromisoformat(form.get("fecha"))
        franja = form.get("franja")
        tipo = form.get("tipo", "completo")
    except (ValueError, TypeError):
        flash(request, "Datos inválidos.", "danger")
        return RedirectResponse(f"/turnos/?semana={semana_str}{perfil_qs}", status_code=303)

    existing = db.query(TurnoVoluntario).filter(
        TurnoVoluntario.voluntario_id == voluntario_id,
        TurnoVoluntario.fecha == fecha,
        TurnoVoluntario.franja == franja,
    ).first()

    if existing:
        return RedirectResponse(f"/turnos/?semana={semana_str}", status_code=303)

    estado = EstadoTurno.medio_turno if tipo == "medio" else EstadoTurno.realizado

    # Regla automática: si hay 2+ veteranos/apoyo_en_junta en el mismo hueco → medio_turno a todos
    PERFILES_VET = {PerfilVoluntario.veterano, PerfilVoluntario.apoyo_en_junta}
    if estado == EstadoTurno.realizado:
        voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
        if voluntario and voluntario.perfil in PERFILES_VET:
            otros_vet = (
                db.query(TurnoVoluntario)
                .join(Voluntario, TurnoVoluntario.voluntario_id == Voluntario.id)
                .filter(
                    TurnoVoluntario.fecha == fecha,
                    TurnoVoluntario.franja == franja,
                    Voluntario.perfil.in_(list(PERFILES_VET)),
                    TurnoVoluntario.voluntario_id != voluntario_id,
                    TurnoVoluntario.estado == EstadoTurno.realizado,
                )
                .all()
            )
            if otros_vet:
                for t in otros_vet:
                    t.estado = EstadoTurno.medio_turno
                estado = EstadoTurno.medio_turno

    db.add(TurnoVoluntario(
        voluntario_id=voluntario_id,
        fecha=fecha,
        franja=franja,
        estado=estado,
    ))
    db.commit()
    return RedirectResponse(f"/turnos/?semana={semana_str}{perfil_qs}", status_code=303)


@router.post("/{turno_id}/eliminar")
async def eliminar_turno(request: Request, turno_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    semana_str = form.get("semana", "")
    perfil_str = form.get("perfil_filtro", "")
    perfil_qs = f"&perfil={perfil_str}" if perfil_str else ""
    turno = db.query(TurnoVoluntario).filter(TurnoVoluntario.id == turno_id).first()
    if turno:
        db.delete(turno)
        db.commit()
    return RedirectResponse(f"/turnos/?semana={semana_str}{perfil_qs}", status_code=303)
