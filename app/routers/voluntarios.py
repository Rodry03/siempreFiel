from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from app.auth import get_current_user
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
from app.database import get_db
from app.models import Voluntario, PerfilVoluntario, EstadoContrato
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


@router.get("/")
def listar_voluntarios(request: Request, perfil: str = "todos", bajas: bool = False, db: Session = Depends(get_db)):
    query = db.query(Voluntario)
    if not bajas:
        query = query.filter(Voluntario.activo == True)
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
        "bajas": bajas,
    })


CONTRATO_LABELS = {
    "pendiente": "Pendiente",
    "enviado": "Enviado",
    "firmado": "Firmado",
}
CONTRATO_COLORS = {
    "pendiente": "secondary",
    "enviado": "warning",
    "firmado": "success",
}


def _contexto_form(extra={}):
    return {
        "perfiles": [p.value for p in PerfilVoluntario],
        "perfil_labels": PERFIL_LABELS,
        "contratos": [e.value for e in EstadoContrato],
        "contrato_labels": CONTRATO_LABELS,
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
    direccion: Optional[str] = Form(None),
    provincia: Optional[str] = Form(None),
    codigo_postal: Optional[str] = Form(None),
    fecha_contrato: Optional[date] = Form(None),
    contrato_estado: Optional[str] = Form(None),
    teaming: Optional[str] = Form(None),
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
        direccion=direccion or None,
        provincia=provincia or None,
        codigo_postal=codigo_postal or None,
        fecha_contrato=fecha_contrato,
        contrato_estado=EstadoContrato(contrato_estado) if contrato_estado else None,
        teaming=teaming == "on",
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
    direccion: Optional[str] = Form(None),
    provincia: Optional[str] = Form(None),
    codigo_postal: Optional[str] = Form(None),
    fecha_contrato: Optional[date] = Form(None),
    contrato_estado: Optional[str] = Form(None),
    teaming: Optional[str] = Form(None),
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
    voluntario.direccion = direccion or None
    voluntario.provincia = provincia or None
    voluntario.codigo_postal = codigo_postal or None
    voluntario.fecha_contrato = fecha_contrato
    voluntario.contrato_estado = EstadoContrato(contrato_estado) if contrato_estado else None
    voluntario.teaming = teaming == "on"
    voluntario.notas = notas or None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(request, "voluntarios/form.html",
            _contexto_form({"voluntario": voluntario, "error": "El email o DNI ya está registrado."}))
    return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)


@router.post("/{voluntario_id}/dar-de-baja")
def dar_de_baja(voluntario_id: int, db: Session = Depends(get_db)):
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if voluntario:
        voluntario.activo = False
        db.commit()
    return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)


@router.post("/{voluntario_id}/reactivar")
def reactivar(voluntario_id: int, db: Session = Depends(get_db)):
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if voluntario:
        voluntario.activo = True
        db.commit()
    return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)


@router.post("/{voluntario_id}/cambiar-perfil")
def cambiar_perfil(voluntario_id: int, perfil: str = Form(...), db: Session = Depends(get_db)):
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if voluntario:
        try:
            voluntario.perfil = PerfilVoluntario(perfil)
            db.commit()
        except ValueError:
            pass
    return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)
