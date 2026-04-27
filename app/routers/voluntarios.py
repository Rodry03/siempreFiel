from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
from app.database import get_db
from app.models import Voluntario, PerfilVoluntario
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


@router.get("/")
def listar_voluntarios(request: Request, perfil: str = "todos", db: Session = Depends(get_db)):
    query = db.query(Voluntario)
    if perfil != "todos":
        try:
            query = query.filter(Voluntario.perfil == PerfilVoluntario(perfil))
        except ValueError:
            pass
    voluntarios = query.order_by(Voluntario.apellido, Voluntario.nombre).all()
    return templates.TemplateResponse(request, "voluntarios/list.html", {
        "voluntarios": voluntarios,
        "perfil_filtro": perfil,
        "perfiles": [p.value for p in PerfilVoluntario],
        "perfil_labels": PERFIL_LABELS,
        "perfil_colors": PERFIL_COLORS,
    })


def _contexto_form(extra={}):
    return {
        "perfiles": [p.value for p in PerfilVoluntario],
        "perfil_labels": PERFIL_LABELS,
        "hoy": date.today().isoformat(),
        **extra,
    }


@router.get("/nuevo")
def form_nuevo_voluntario(
    request: Request,
    nombre: str = "",
    apellido: str = "",
    email: str = "",
    telefono: str = "",
):
    prefill = {"nombre": nombre, "apellido": apellido, "email": email, "telefono": telefono}
    return templates.TemplateResponse(request, "voluntarios/form.html",
        _contexto_form({"voluntario": None, "prefill": prefill}))


@router.post("/nuevo")
def crear_voluntario(
    request: Request,
    nombre: str = Form(...),
    apellido: str = Form(...),
    dni: Optional[str] = Form(None),
    email: str = Form(...),
    perfil: str = Form(...),
    fecha_alta: date = Form(...),
    activo: Optional[str] = Form(None),
    ppp: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    voluntario = Voluntario(
        nombre=nombre,
        apellido=apellido,
        dni=dni or None,
        email=email,
        perfil=PerfilVoluntario(perfil),
        fecha_alta=fecha_alta,
        activo=activo == "on",
        ppp=ppp == "on",
        telefono=telefono or None,
        notas=notas or None,
    )
    db.add(voluntario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(request, "voluntarios/form.html",
            _contexto_form({"voluntario": voluntario, "error": "El email o DNI ya está registrado."}))
    return RedirectResponse("/voluntarios/", status_code=303)


@router.get("/{voluntario_id}/editar")
def form_editar_voluntario(request: Request, voluntario_id: int, db: Session = Depends(get_db)):
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if not voluntario:
        return RedirectResponse("/voluntarios/", status_code=303)
    return templates.TemplateResponse(request, "voluntarios/form.html",
        _contexto_form({"voluntario": voluntario}))


@router.post("/{voluntario_id}/editar")
def editar_voluntario(
    request: Request,
    voluntario_id: int,
    nombre: str = Form(...),
    apellido: str = Form(...),
    dni: Optional[str] = Form(None),
    email: str = Form(...),
    perfil: str = Form(...),
    fecha_alta: date = Form(...),
    activo: Optional[str] = Form(None),
    ppp: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if not voluntario:
        return RedirectResponse("/voluntarios/", status_code=303)
    voluntario.nombre = nombre
    voluntario.apellido = apellido
    voluntario.dni = dni or None
    voluntario.email = email
    voluntario.perfil = PerfilVoluntario(perfil)
    voluntario.fecha_alta = fecha_alta
    voluntario.activo = activo == "on"
    voluntario.ppp = ppp == "on"
    voluntario.telefono = telefono or None
    voluntario.notas = notas or None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(request, "voluntarios/form.html",
            _contexto_form({"voluntario": voluntario, "error": "El email o DNI ya está registrado."}))
    return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)
