from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.templates_config import templates
from app.auth import get_current_user, require_not_veterano
from app.models import GrupoTarea, MiembroGrupoTarea, EjecucionGrupoTarea, Voluntario

router = APIRouter(prefix="/tareas", dependencies=[Depends(get_current_user)])


def _semana_actual() -> date:
    hoy = date.today()
    return hoy - timedelta(days=hoy.weekday())


def _ejecucion_semana(db: Session, grupo_id: int, semana: date) -> Optional[EjecucionGrupoTarea]:
    return db.query(EjecucionGrupoTarea).filter(
        EjecucionGrupoTarea.grupo_id == grupo_id,
        EjecucionGrupoTarea.semana == semana,
    ).first()


def _voluntarios_disponibles(db: Session):
    return db.query(Voluntario).filter(Voluntario.activo == True).order_by(Voluntario.nombre).all()


@router.get("/")
def lista_tareas(request: Request, db: Session = Depends(get_db)):
    semana = _semana_actual()
    grupos = db.query(GrupoTarea).order_by(GrupoTarea.nombre).all()
    ejecuciones = {e.grupo_id: e for e in db.query(EjecucionGrupoTarea).filter(
        EjecucionGrupoTarea.semana == semana
    ).all()}
    return templates.TemplateResponse(request, "tareas/list.html", {
        "grupos": grupos,
        "ejecuciones": ejecuciones,
        "semana": semana,
    })


@router.get("/{grupo_id}")
def detalle_tarea(request: Request, grupo_id: int, db: Session = Depends(get_db)):
    grupo = db.query(GrupoTarea).filter(GrupoTarea.id == grupo_id).first()
    if not grupo:
        return RedirectResponse("/tareas/", status_code=303)
    semana = _semana_actual()
    ejecucion_actual = _ejecucion_semana(db, grupo_id, semana)
    voluntarios = _voluntarios_disponibles(db)
    miembro_ids = {m.voluntario_id for m in grupo.miembros}
    return templates.TemplateResponse(request, "tareas/detail.html", {
        "grupo": grupo,
        "semana": semana,
        "ejecucion_actual": ejecucion_actual,
        "voluntarios": voluntarios,
        "miembro_ids": miembro_ids,
    })


@router.post("/{grupo_id}/editar", dependencies=[Depends(require_not_veterano)])
def editar_tarea(
    grupo_id: int,
    descripcion: Optional[str] = Form(None),
    capitan_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    grupo = db.query(GrupoTarea).filter(GrupoTarea.id == grupo_id).first()
    if not grupo:
        return RedirectResponse("/tareas/", status_code=303)
    grupo.descripcion = descripcion or None
    grupo.capitan_id = capitan_id or None
    db.commit()
    return RedirectResponse(f"/tareas/{grupo_id}", status_code=303)


@router.post("/{grupo_id}/miembro", dependencies=[Depends(require_not_veterano)])
def añadir_miembro(
    grupo_id: int,
    voluntario_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    if not voluntario_id:
        return RedirectResponse(f"/tareas/{grupo_id}", status_code=303)
    existe = db.query(MiembroGrupoTarea).filter(
        MiembroGrupoTarea.grupo_id == grupo_id,
        MiembroGrupoTarea.voluntario_id == voluntario_id,
    ).first()
    if not existe:
        db.add(MiembroGrupoTarea(grupo_id=grupo_id, voluntario_id=voluntario_id))
        db.commit()
    return RedirectResponse(f"/tareas/{grupo_id}", status_code=303)


@router.post("/{grupo_id}/miembro/{voluntario_id}/eliminar", dependencies=[Depends(require_not_veterano)])
def eliminar_miembro(grupo_id: int, voluntario_id: int, db: Session = Depends(get_db)):
    db.query(MiembroGrupoTarea).filter(
        MiembroGrupoTarea.grupo_id == grupo_id,
        MiembroGrupoTarea.voluntario_id == voluntario_id,
    ).delete()
    db.commit()
    return RedirectResponse(f"/tareas/{grupo_id}", status_code=303)


@router.post("/{grupo_id}/ejecucion")
def registrar_ejecucion(
    grupo_id: int,
    realizado: Optional[str] = Form(None),
    ejecutor_id: Optional[int] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    semana = _semana_actual()
    ejecucion = _ejecucion_semana(db, grupo_id, semana)
    if ejecucion:
        ejecucion.realizado = realizado == "on"
        ejecucion.ejecutor_id = ejecutor_id or None
        ejecucion.notas = notas or None
    else:
        db.add(EjecucionGrupoTarea(
            grupo_id=grupo_id,
            semana=semana,
            realizado=realizado == "on",
            ejecutor_id=ejecutor_id or None,
            notas=notas or None,
        ))
    db.commit()
    return RedirectResponse(f"/tareas/{grupo_id}", status_code=303)
