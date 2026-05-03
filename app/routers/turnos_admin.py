from datetime import date, timedelta
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.auth import get_current_user, require_not_veterano, flash
from app.database import get_db
from app.models import TurnoVoluntario, Voluntario, FranjaTurno, EstadoTurno, PerfilVoluntario
from app.templates_config import templates
from app.routers.turnos import FRANJA_LABELS, ESTADO_LABELS, ESTADO_COLORS, PERFILES_SIN_TURNOS

router = APIRouter(
    prefix="/turnos",
    dependencies=[Depends(get_current_user), Depends(require_not_veterano)],
)


def _redirect_turnos(semana: str, voluntario_id_filtro: str, estado_filtro: str) -> str:
    params = f"semana={semana}"
    if voluntario_id_filtro:
        params += f"&voluntario_id={voluntario_id_filtro}"
    if estado_filtro:
        params += f"&estado={estado_filtro}"
    return f"/turnos/?{params}"


@router.get("/")
def lista_turnos(
    request: Request,
    semana: Optional[str] = None,
    voluntario_id: Optional[int] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
):
    hoy = date.today()
    if semana:
        base = date.fromisoformat(semana)
        lunes = base - timedelta(days=base.weekday())
    else:
        lunes = hoy - timedelta(days=hoy.weekday())
    domingo = lunes + timedelta(days=6)

    query = db.query(TurnoVoluntario).filter(
        TurnoVoluntario.fecha >= lunes,
        TurnoVoluntario.fecha <= domingo,
    )
    if voluntario_id:
        query = query.filter(TurnoVoluntario.voluntario_id == voluntario_id)
    if estado:
        query = query.filter(TurnoVoluntario.estado == EstadoTurno(estado))

    turnos = query.order_by(TurnoVoluntario.fecha, TurnoVoluntario.franja).all()

    voluntarios = db.query(Voluntario).filter(
        Voluntario.activo == True,
        Voluntario.perfil.notin_(list(PERFILES_SIN_TURNOS)),
    ).order_by(Voluntario.nombre).all()

    semana_anterior = (lunes - timedelta(days=7)).isoformat()
    semana_siguiente = (lunes + timedelta(days=7)).isoformat()

    return templates.TemplateResponse(request, "turnos/list.html", {
        "turnos": turnos,
        "voluntarios": voluntarios,
        "franja_labels": FRANJA_LABELS,
        "estado_labels": ESTADO_LABELS,
        "estado_colors": ESTADO_COLORS,
        "estados": [e.value for e in EstadoTurno],
        "franjas": [f.value for f in FranjaTurno],
        "lunes": lunes,
        "domingo": domingo,
        "semana": lunes.isoformat(),
        "semana_anterior": semana_anterior,
        "semana_siguiente": semana_siguiente,
        "voluntario_id_filtro": voluntario_id or "",
        "estado_filtro": estado or "",
        "hoy": hoy.isoformat(),
    })


@router.post("/{turno_id}/editar")
def editar_turno(
    request: Request,
    turno_id: int,
    fecha: date = Form(...),
    franja: str = Form(...),
    estado: str = Form(...),
    notas: Optional[str] = Form(None),
    semana: str = Form(""),
    voluntario_id_filtro: str = Form(""),
    estado_filtro: str = Form(""),
    db: Session = Depends(get_db),
):
    turno = db.query(TurnoVoluntario).filter(TurnoVoluntario.id == turno_id).first()
    if turno:
        turno.fecha = fecha
        turno.franja = FranjaTurno(franja)
        turno.estado = EstadoTurno(estado)
        turno.notas = notas or None
        db.commit()
        flash(request, "Turno actualizado.")
    return RedirectResponse(
        _redirect_turnos(semana, voluntario_id_filtro, estado_filtro),
        status_code=303,
    )


@router.post("/nuevo")
def crear_turno(
    request: Request,
    voluntario_id: int = Form(...),
    fecha: date = Form(...),
    franja: str = Form(...),
    estado: str = Form(...),
    notas: Optional[str] = Form(None),
    semana: str = Form(""),
    voluntario_id_filtro: str = Form(""),
    estado_filtro: str = Form(""),
    db: Session = Depends(get_db),
):
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if voluntario:
        db.add(TurnoVoluntario(
            voluntario_id=voluntario_id,
            fecha=fecha,
            franja=FranjaTurno(franja),
            estado=EstadoTurno(estado),
            notas=notas or None,
        ))
        db.commit()
        flash(request, "Turno añadido.")
    return RedirectResponse(
        _redirect_turnos(semana, voluntario_id_filtro, estado_filtro),
        status_code=303,
    )


@router.post("/{turno_id}/eliminar")
def eliminar_turno_admin(
    request: Request,
    turno_id: int,
    semana: str = Form(""),
    voluntario_id_filtro: str = Form(""),
    estado_filtro: str = Form(""),
    db: Session = Depends(get_db),
):
    turno = db.query(TurnoVoluntario).filter(TurnoVoluntario.id == turno_id).first()
    if turno:
        db.delete(turno)
        db.commit()
        flash(request, "Turno eliminado.", "warning")
    return RedirectResponse(
        _redirect_turnos(semana, voluntario_id_filtro, estado_filtro),
        status_code=303,
    )
