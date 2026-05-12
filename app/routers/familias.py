import logging
import os
from datetime import date
import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from app.auth import get_current_user, require_not_veterano, flash
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
from app.database import get_db
from app.models import Familia, Perro, EstadoPerro
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/familias", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])

TIPO_LABELS = {"adopcion": "Adopción", "acogida": "Acogida"}
TIPO_COLORS = {"adopcion": "success", "acogida": "primary"}


@router.get("/")
def listar_familias(request: Request, tipo: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Familia)
    if tipo in TIPO_LABELS:
        query = query.filter(Familia.tipo == tipo)
    familias = query.order_by(Familia.apellidos.asc(), Familia.nombre.asc()).all()
    return templates.TemplateResponse(request, "familias/list.html", {
        "familias": familias,
        "tipo_filtro": tipo or "",
        "tipo_labels": TIPO_LABELS,
        "tipo_colors": TIPO_COLORS,
    })


@router.get("/nueva")
def nueva_familia_form(request: Request, db: Session = Depends(get_db)):
    perros = db.query(Perro).filter(Perro.estado != EstadoPerro.fallecido).order_by(Perro.nombre).all()
    return templates.TemplateResponse(request, "familias/form.html", {
        "familia": None,
        "perros": perros,
        "tipo_labels": TIPO_LABELS,
        "hoy": date.today().isoformat(),
    })


@router.post("/nueva")
def crear_familia(
    request: Request,
    nombre: str = Form(...),
    apellidos: str = Form(...),
    dni: str = Form(...),
    tipo: Optional[str] = Form(None),
    perro_id: Optional[int] = Form(None),
    email: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    direccion: Optional[str] = Form(None),
    municipio: Optional[str] = Form(None),
    provincia: Optional[str] = Form(None),
    codigo_postal: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    fecha_contrato: date = Form(...),
    db: Session = Depends(get_db),
):
    familia = Familia(
        nombre=nombre.strip(),
        apellidos=apellidos.strip(),
        dni=dni.strip().upper(),
        tipo=tipo or None,
        perro_id=perro_id or None,
        email=email or None,
        telefono=telefono or None,
        direccion=direccion or None,
        municipio=municipio or None,
        provincia=provincia or None,
        codigo_postal=codigo_postal or None,
        notas=notas or None,
        fecha_contrato=fecha_contrato,
    )
    db.add(familia)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "Ya existe una familia con ese DNI.", "danger")
        perros = db.query(Perro).filter(Perro.estado != EstadoPerro.fallecido).order_by(Perro.nombre).all()
        return templates.TemplateResponse(request, "familias/form.html", {
            "familia": None,
            "perros": perros,
            "tipo_labels": TIPO_LABELS,
            "hoy": fecha_contrato.isoformat(),
        })
    return RedirectResponse(f"/familias/{familia.id}", status_code=303)


@router.get("/{familia_id}")
def detalle_familia(request: Request, familia_id: int, db: Session = Depends(get_db)):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if not familia:
        return RedirectResponse("/familias/", status_code=303)
    return templates.TemplateResponse(request, "familias/detail.html", {
        "familia": familia,
        "tipo_labels": TIPO_LABELS,
        "tipo_colors": TIPO_COLORS,
    })


@router.get("/{familia_id}/editar")
def editar_familia_form(request: Request, familia_id: int, db: Session = Depends(get_db)):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if not familia:
        return RedirectResponse("/familias/", status_code=303)
    perros = db.query(Perro).filter(Perro.estado != EstadoPerro.fallecido).order_by(Perro.nombre).all()
    return templates.TemplateResponse(request, "familias/form.html", {
        "familia": familia,
        "perros": perros,
        "tipo_labels": TIPO_LABELS,
        "hoy": date.today().isoformat(),
    })


@router.post("/{familia_id}/editar")
def editar_familia(
    request: Request,
    familia_id: int,
    nombre: str = Form(...),
    apellidos: str = Form(...),
    dni: str = Form(...),
    tipo: Optional[str] = Form(None),
    perro_id: Optional[int] = Form(None),
    email: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    direccion: Optional[str] = Form(None),
    municipio: Optional[str] = Form(None),
    provincia: Optional[str] = Form(None),
    codigo_postal: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    fecha_contrato: date = Form(...),
    db: Session = Depends(get_db),
):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if not familia:
        return RedirectResponse("/familias/", status_code=303)
    familia.nombre = nombre.strip()
    familia.apellidos = apellidos.strip()
    familia.dni = dni.strip().upper()
    familia.tipo = tipo or None
    familia.perro_id = perro_id or None
    familia.email = email or None
    familia.telefono = telefono or None
    familia.direccion = direccion or None
    familia.municipio = municipio or None
    familia.provincia = provincia or None
    familia.codigo_postal = codigo_postal or None
    familia.notas = notas or None
    familia.fecha_contrato = fecha_contrato
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "Ya existe una familia con ese DNI.", "danger")
    return RedirectResponse(f"/familias/{familia_id}", status_code=303)


@router.post("/{familia_id}/eliminar")
def eliminar_familia(familia_id: int, db: Session = Depends(get_db)):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if familia:
        db.delete(familia)
        db.commit()
    return RedirectResponse("/familias/", status_code=303)


def _subir_contrato_familia(file: UploadFile, familia_id: int) -> tuple:
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    )
    contents = file.file.read()
    result = cloudinary.uploader.upload(
        contents,
        resource_type="raw",
        folder="protectora/contratos",
        public_id=f"contrato_familia_{familia_id}",
        overwrite=True,
    )
    return result["secure_url"], file.filename


@router.post("/{familia_id}/contrato-firmado")
def subir_contrato_firmado(
    request: Request,
    familia_id: int,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if not familia:
        return RedirectResponse("/familias/", status_code=303)
    try:
        url, nombre = _subir_contrato_familia(archivo, familia_id)
        familia.contrato_firmado_url = url
        familia.contrato_firmado_fecha = date.today()
        familia.contrato_firmado_nombre = nombre
        db.commit()
        flash(request, "Contrato firmado subido correctamente.")
    except Exception as e:
        logger.error("Error subiendo contrato firmado familia: %s", e)
        flash(request, "Error al subir el contrato.", "danger")
    return RedirectResponse(f"/familias/{familia_id}", status_code=303)


@router.post("/{familia_id}/contrato-firmado/eliminar")
def eliminar_contrato_firmado(
    request: Request,
    familia_id: int,
    db: Session = Depends(get_db),
):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if familia and familia.contrato_firmado_url:
        try:
            cloudinary.config(
                cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
                api_key=os.environ.get("CLOUDINARY_API_KEY"),
                api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
            )
            cloudinary.uploader.destroy(
                f"protectora/contratos/contrato_familia_{familia_id}",
                resource_type="raw",
            )
        except Exception as e:
            logger.warning("Error eliminando contrato familia de Cloudinary: %s", e)
        familia.contrato_firmado_url = None
        familia.contrato_firmado_fecha = None
        familia.contrato_firmado_nombre = None
        db.commit()
        flash(request, "Contrato eliminado.")
    return RedirectResponse(f"/familias/{familia_id}", status_code=303)
