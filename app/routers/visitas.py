from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
from app.database import get_db
from app.models import Visitante, EstadoVisitante
from app.templates_config import templates

router = APIRouter(prefix="/visitas")

ESTADO_LABELS = {
    "interesado": "Interesado",
    "visita_programada": "Visita programada",
    "visita_realizada": "Visita realizada",
    "se_convirtio": "Se convirtió",
    "descartado": "Descartado",
}
ESTADO_COLORS = {
    "interesado": "secondary",
    "visita_programada": "primary",
    "visita_realizada": "warning",
    "se_convirtio": "success",
    "descartado": "danger",
}


def _estado_con_fecha(estado: EstadoVisitante, fecha_visita) -> EstadoVisitante:
    if fecha_visita and estado == EstadoVisitante.interesado:
        if fecha_visita <= date.today():
            return EstadoVisitante.visita_realizada
        return EstadoVisitante.visita_programada
    return estado


def _contexto_base():
    return {
        "estados": [e.value for e in EstadoVisitante],
        "estado_labels": ESTADO_LABELS,
        "estado_colors": ESTADO_COLORS,
        "hoy": date.today(),
    }


@router.get("/")
def listar_visitas(request: Request, estado: str = "todos", db: Session = Depends(get_db)):
    query = db.query(Visitante)
    if estado != "todos":
        try:
            query = query.filter(Visitante.estado == EstadoVisitante(estado))
        except ValueError:
            pass
    visitantes = query.order_by(Visitante.fecha_contacto.desc()).all()
    return templates.TemplateResponse(request, "visitas/list.html", {
        **_contexto_base(),
        "visitantes": visitantes,
        "estado_filtro": estado,
    })


@router.get("/nuevo")
def form_nuevo_visitante(request: Request):
    return templates.TemplateResponse(request, "visitas/form.html", {
        **_contexto_base(),
        "visitante": None,
    })


@router.post("/nuevo")
def crear_visitante(
    request: Request,
    nombre: str = Form(...),
    apellido: str = Form(...),
    email: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    fecha_contacto: date = Form(...),
    fecha_visita: Optional[date] = Form(None),
    estado: str = Form(...),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    estado_final = _estado_con_fecha(EstadoVisitante(estado), fecha_visita)
    visitante = Visitante(
        nombre=nombre,
        apellido=apellido,
        email=email or None,
        telefono=telefono or None,
        fecha_contacto=fecha_contacto,
        fecha_visita=fecha_visita,
        estado=estado_final,
        notas=notas or None,
    )
    db.add(visitante)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(request, "visitas/form.html", {
            **_contexto_base(),
            "visitante": visitante,
            "error": "El email ya está registrado.",
        })
    return RedirectResponse("/visitas/", status_code=303)


@router.get("/{visitante_id}")
def detalle_visitante(request: Request, visitante_id: int, db: Session = Depends(get_db)):
    visitante = db.query(Visitante).filter(Visitante.id == visitante_id).first()
    if not visitante:
        return RedirectResponse("/visitas/", status_code=303)
    return templates.TemplateResponse(request, "visitas/detail.html", {
        **_contexto_base(),
        "visitante": visitante,
    })


@router.get("/{visitante_id}/editar")
def form_editar_visitante(request: Request, visitante_id: int, db: Session = Depends(get_db)):
    visitante = db.query(Visitante).filter(Visitante.id == visitante_id).first()
    if not visitante:
        return RedirectResponse("/visitas/", status_code=303)
    return templates.TemplateResponse(request, "visitas/form.html", {
        **_contexto_base(),
        "visitante": visitante,
    })


@router.post("/{visitante_id}/editar")
def editar_visitante(
    request: Request,
    visitante_id: int,
    nombre: str = Form(...),
    apellido: str = Form(...),
    email: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    fecha_contacto: date = Form(...),
    fecha_visita: Optional[date] = Form(None),
    estado: str = Form(...),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    visitante = db.query(Visitante).filter(Visitante.id == visitante_id).first()
    if not visitante:
        return RedirectResponse("/visitas/", status_code=303)
    visitante.nombre = nombre
    visitante.apellido = apellido
    visitante.email = email or None
    visitante.telefono = telefono or None
    visitante.fecha_contacto = fecha_contacto
    visitante.fecha_visita = fecha_visita
    visitante.estado = _estado_con_fecha(EstadoVisitante(estado), fecha_visita)
    visitante.notas = notas or None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(request, "visitas/form.html", {
            **_contexto_base(),
            "visitante": visitante,
            "error": "El email ya está registrado.",
        })
    return RedirectResponse(f"/visitas/{visitante_id}", status_code=303)


@router.post("/{visitante_id}/convertir")
def convertir_en_voluntario(visitante_id: int, db: Session = Depends(get_db)):
    visitante = db.query(Visitante).filter(Visitante.id == visitante_id).first()
    if not visitante:
        return RedirectResponse("/visitas/", status_code=303)
    visitante.estado = EstadoVisitante.se_convirtio
    db.commit()
    params = f"nombre={visitante.nombre}&apellido={visitante.apellido}"
    if visitante.email:
        params += f"&email={visitante.email}"
    if visitante.telefono:
        params += f"&telefono={visitante.telefono}"
    return RedirectResponse(f"/voluntarios/nuevo?{params}", status_code=303)
