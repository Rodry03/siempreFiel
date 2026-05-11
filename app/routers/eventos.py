from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import flash, get_current_user, require_not_veterano
from app.database import get_db
from app.models import Evento, EventoVoluntario, Voluntario
from app.templates_config import templates

router = APIRouter(prefix="/eventos", tags=["eventos"])

TIPOS_LABELS = {
    "mercadillo":      "Mercadillo",
    "feria_adopcion":  "Feria de adopción",
    "charla":          "Charla",
    "captacion":       "Captación",
    "paseo_solidario": "Paseo solidario",
    "otro":            "Otro",
}
TIPOS = list(TIPOS_LABELS.keys())


def _tipos_list(evento) -> list:
    if not evento or not evento.tipo:
        return []
    return [t for t in evento.tipo.split(",") if t]


@router.get("/", dependencies=[Depends(get_current_user)])
def lista_eventos(request: Request, db: Session = Depends(get_db)):
    eventos = db.query(Evento).order_by(Evento.fecha.desc()).all()
    return templates.TemplateResponse(request, "eventos/list.html", {
        "eventos": eventos,
        "tipos_labels": TIPOS_LABELS,
        "tipos_list": _tipos_list,
    })


@router.get("/nuevo", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])
def nuevo_form(request: Request):
    return templates.TemplateResponse(request, "eventos/form.html", {
        "evento": None,
        "tipos": TIPOS,
        "tipos_labels": TIPOS_LABELS,
        "evento_tipos": [],
    })


@router.post("/nuevo", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])
def crear_evento(
    request: Request,
    titulo: str = Form(...),
    fecha: date = Form(...),
    hora_inicio: Optional[str] = Form(None),
    hora_fin: Optional[str] = Form(None),
    ubicacion: Optional[str] = Form(None),
    tipo: List[str] = Form(default=[]),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    evento = Evento(
        titulo=titulo.strip(),
        fecha=fecha,
        hora_inicio=hora_inicio or None,
        hora_fin=hora_fin or None,
        ubicacion=ubicacion.strip() if ubicacion else None,
        tipo=",".join(tipo) if tipo else None,
        notas=notas.strip() if notas else None,
    )
    db.add(evento)
    db.commit()
    db.refresh(evento)
    flash(request, "Evento creado.", "success")
    return RedirectResponse(f"/eventos/{evento.id}", status_code=303)


@router.get("/{evento_id}", dependencies=[Depends(get_current_user)])
def detalle_evento(request: Request, evento_id: int, db: Session = Depends(get_db)):
    evento = db.query(Evento).filter(Evento.id == evento_id).first()
    if not evento:
        raise HTTPException(status_code=404)
    asignados_ids = {ev.voluntario_id for ev in evento.participantes}
    query = db.query(Voluntario).filter(Voluntario.activo == True)
    if asignados_ids:
        query = query.filter(Voluntario.id.notin_(asignados_ids))
    voluntarios_disponibles = query.order_by(Voluntario.nombre, Voluntario.apellido).all()
    return templates.TemplateResponse(request, "eventos/detail.html", {
        "evento": evento,
        "tipos_labels": TIPOS_LABELS,
        "evento_tipos": _tipos_list(evento),
        "voluntarios_disponibles": voluntarios_disponibles,
    })


@router.get("/{evento_id}/editar", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])
def editar_form(request: Request, evento_id: int, db: Session = Depends(get_db)):
    evento = db.query(Evento).filter(Evento.id == evento_id).first()
    if not evento:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "eventos/form.html", {
        "evento": evento,
        "tipos": TIPOS,
        "tipos_labels": TIPOS_LABELS,
        "evento_tipos": _tipos_list(evento),
    })


@router.post("/{evento_id}/editar", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])
def editar_evento(
    request: Request,
    evento_id: int,
    titulo: str = Form(...),
    fecha: date = Form(...),
    hora_inicio: Optional[str] = Form(None),
    hora_fin: Optional[str] = Form(None),
    ubicacion: Optional[str] = Form(None),
    tipo: List[str] = Form(default=[]),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    evento = db.query(Evento).filter(Evento.id == evento_id).first()
    if not evento:
        raise HTTPException(status_code=404)
    evento.titulo = titulo.strip()
    evento.fecha = fecha
    evento.hora_inicio = hora_inicio or None
    evento.hora_fin = hora_fin or None
    evento.ubicacion = ubicacion.strip() if ubicacion else None
    evento.tipo = ",".join(tipo) if tipo else None
    evento.notas = notas.strip() if notas else None
    db.commit()
    flash(request, "Evento actualizado.", "success")
    return RedirectResponse(f"/eventos/{evento_id}", status_code=303)


@router.post("/{evento_id}/eliminar", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])
def eliminar_evento(request: Request, evento_id: int, db: Session = Depends(get_db)):
    evento = db.query(Evento).filter(Evento.id == evento_id).first()
    if evento:
        db.delete(evento)
        db.commit()
    flash(request, "Evento eliminado.", "success")
    return RedirectResponse("/eventos/", status_code=303)


@router.post("/{evento_id}/voluntario", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])
def agregar_voluntario(
    request: Request,
    evento_id: int,
    voluntario_id: int = Form(...),
    db: Session = Depends(get_db),
):
    existe = db.query(EventoVoluntario).filter(
        EventoVoluntario.evento_id == evento_id,
        EventoVoluntario.voluntario_id == voluntario_id,
    ).first()
    if not existe:
        db.add(EventoVoluntario(evento_id=evento_id, voluntario_id=voluntario_id))
        db.commit()
    return RedirectResponse(f"/eventos/{evento_id}", status_code=303)


@router.post("/{evento_id}/voluntario/{voluntario_id}/eliminar", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])
def quitar_voluntario(
    request: Request,
    evento_id: int,
    voluntario_id: int,
    db: Session = Depends(get_db),
):
    ev = db.query(EventoVoluntario).filter(
        EventoVoluntario.evento_id == evento_id,
        EventoVoluntario.voluntario_id == voluntario_id,
    ).first()
    if ev:
        db.delete(ev)
        db.commit()
    return RedirectResponse(f"/eventos/{evento_id}", status_code=303)
