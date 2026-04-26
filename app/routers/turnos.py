from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Voluntario, TurnoVoluntario, FranjaTurno, EstadoTurno, PerfilVoluntario
from app.templates_config import templates

router = APIRouter(prefix="/voluntarios")

PERFIL_LABELS = {
    "directiva": "Directiva",
    "veterano": "Veterano",
    "voluntario": "Voluntario",
    "guagua": "Guagua",
    "eventos": "Eventos",
    "colaboradores": "Colaboradores",
}
PERFIL_COLORS = {
    "directiva": "danger",
    "veterano": "warning",
    "voluntario": "success",
    "guagua": "primary",
    "eventos": "info",
    "colaboradores": "secondary",
}

PERFILES_SIN_TURNOS = {
    PerfilVoluntario.directiva,
    PerfilVoluntario.guagua,
    PerfilVoluntario.eventos,
    PerfilVoluntario.colaboradores,
}
FRANJA_LABELS = {
    "manana": "Mañana",
    "tarde": "Tarde",
}
ESTADO_LABELS = {
    "realizado": "Realizado",
    "medio_turno": "Medio turno",
    "falta_justificada": "Falta justificada",
    "falta_injustificada": "Falta injustificada",
    "no_apuntado": "No apuntado",
}
ESTADO_COLORS = {
    "realizado": "success",
    "medio_turno": "info",
    "falta_justificada": "warning",
    "falta_injustificada": "danger",
    "no_apuntado": "secondary",
}
ESTADO_VALOR = {
    "realizado": 1.0,
    "medio_turno": 0.5,
    "falta_justificada": 0.0,
    "falta_injustificada": 0.0,
    "no_apuntado": 0.0,
}


FECHA_INICIO_TURNOS = date(2026, 4, 1)


def calcular_saldo(voluntario: Voluntario) -> float:
    fecha_inicio = max(FECHA_INICIO_TURNOS, voluntario.fecha_alta)
    semanas_activo = (date.today() - fecha_inicio).days // 7
    turnos_acumulados = sum(ESTADO_VALOR[t.estado.value] for t in voluntario.turnos)
    return turnos_acumulados - semanas_activo


@router.get("/{voluntario_id}")
def detalle_voluntario(request: Request, voluntario_id: int, db: Session = Depends(get_db)):
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if not voluntario:
        return RedirectResponse("/voluntarios/", status_code=303)
    hace_turnos = voluntario.perfil not in PERFILES_SIN_TURNOS
    saldo = calcular_saldo(voluntario) if hace_turnos else None
    return templates.TemplateResponse(request, "voluntarios/detail.html", {
        "voluntario": voluntario,
        "hace_turnos": hace_turnos,
        "saldo": saldo,
        "perfil_labels": PERFIL_LABELS,
        "perfil_colors": PERFIL_COLORS,
        "franja_labels": FRANJA_LABELS,
        "estado_labels": ESTADO_LABELS,
        "estado_colors": ESTADO_COLORS,
        "franjas": [f.value for f in FranjaTurno],
        "estados": [e.value for e in EstadoTurno],
        "hoy": date.today().isoformat(),
    })


@router.post("/{voluntario_id}/turno")
def registrar_turno(
    voluntario_id: int,
    fecha: date = Form(...),
    franja: str = Form(...),
    estado: str = Form(...),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if not voluntario:
        return RedirectResponse("/voluntarios/", status_code=303)
    turno = TurnoVoluntario(
        voluntario_id=voluntario_id,
        fecha=fecha,
        franja=FranjaTurno(franja),
        estado=EstadoTurno(estado),
        notas=notas or None,
    )
    db.add(turno)
    db.commit()
    return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)


@router.post("/{voluntario_id}/turno/{turno_id}/eliminar")
def eliminar_turno(voluntario_id: int, turno_id: int, db: Session = Depends(get_db)):
    turno = db.query(TurnoVoluntario).filter(
        TurnoVoluntario.id == turno_id,
        TurnoVoluntario.voluntario_id == voluntario_id,
    ).first()
    if turno:
        db.delete(turno)
        db.commit()
    return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)
