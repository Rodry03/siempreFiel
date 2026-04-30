from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from app.auth import get_current_user, require_not_veterano
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Voluntario, TurnoVoluntario, FranjaTurno, EstadoTurno, PerfilVoluntario
from app.routers.voluntarios import CONTRATO_LABELS, CONTRATO_COLORS
from app.templates_config import templates

router = APIRouter(prefix="/voluntarios", dependencies=[Depends(get_current_user)])

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


def calcular_tiempo_voluntario(fecha_alta) -> str:
    hoy = date.today()
    anos = hoy.year - fecha_alta.year - ((hoy.month, hoy.day) < (fecha_alta.month, fecha_alta.day))
    if anos == 0:
        meses = (hoy.year - fecha_alta.year) * 12 + hoy.month - fecha_alta.month
        if hoy.day < fecha_alta.day:
            meses -= 1
        return f"{meses} mes{'es' if meses != 1 else ''}"
    return f"{anos} año{'s' if anos != 1 else ''}"


def calcular_saldo(voluntario: Voluntario) -> float:
    fecha_inicio = max(FECHA_INICIO_TURNOS, voluntario.fecha_alta)
    semanas_activo = (date.today() - fecha_inicio).days // 7
    turnos_acumulados = sum(ESTADO_VALOR[t.estado.value] for t in voluntario.turnos)
    return turnos_acumulados - semanas_activo


@router.get("/{voluntario_id}")
def detalle_voluntario(request: Request, voluntario_id: int, db: Session = Depends(get_db)):
    from app.models import RolUsuario
    current_user = request.state.current_user
    if current_user.rol == RolUsuario.veterano:
        if not current_user.voluntario_id or current_user.voluntario_id != voluntario_id:
            from app.auth import NotAuthorized
            raise NotAuthorized()
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if not voluntario:
        return RedirectResponse("/voluntarios/", status_code=303)
    hace_turnos = voluntario.perfil not in PERFILES_SIN_TURNOS
    saldo = calcular_saldo(voluntario) if hace_turnos else None
    total_turnos = sum(ESTADO_VALOR[t.estado.value] for t in voluntario.turnos)
    tiempo_voluntario = calcular_tiempo_voluntario(voluntario.fecha_alta)

    from app.models import MiembroGrupoTarea, EjecucionGrupoTarea
    from datetime import timedelta
    hoy = date.today()
    semana_actual = hoy - timedelta(days=hoy.weekday())
    memberships = db.query(MiembroGrupoTarea).filter(MiembroGrupoTarea.voluntario_id == voluntario_id).all()
    grupos_voluntario = []
    for m in memberships:
        ej = db.query(EjecucionGrupoTarea).filter(
            EjecucionGrupoTarea.grupo_id == m.grupo_id,
            EjecucionGrupoTarea.semana == semana_actual,
        ).first()
        grupos_voluntario.append({"grupo": m.grupo, "ejecucion": ej})

    return templates.TemplateResponse(request, "voluntarios/detail.html", {
        "voluntario": voluntario,
        "hace_turnos": hace_turnos,
        "saldo": saldo,
        "perfiles": [p.value for p in PerfilVoluntario],
        "perfil_labels": PERFIL_LABELS,
        "perfil_colors": PERFIL_COLORS,
        "contrato_labels": CONTRATO_LABELS,
        "contrato_colors": CONTRATO_COLORS,
        "franja_labels": FRANJA_LABELS,
        "estado_labels": ESTADO_LABELS,
        "estado_colors": ESTADO_COLORS,
        "franjas": [f.value for f in FranjaTurno],
        "estados": [e.value for e in EstadoTurno],
        "hoy": hoy.isoformat(),
        "total_turnos": total_turnos,
        "tiempo_voluntario": tiempo_voluntario,
        "grupos_voluntario": grupos_voluntario,
        "semana_actual": semana_actual,
    })


@router.post("/{voluntario_id}/turno", dependencies=[Depends(require_not_veterano)])
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


@router.post("/{voluntario_id}/turno/{turno_id}/eliminar", dependencies=[Depends(require_not_veterano)])
def eliminar_turno(voluntario_id: int, turno_id: int, db: Session = Depends(get_db)):
    turno = db.query(TurnoVoluntario).filter(
        TurnoVoluntario.id == turno_id,
        TurnoVoluntario.voluntario_id == voluntario_id,
    ).first()
    if turno:
        db.delete(turno)
        db.commit()
    return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)
