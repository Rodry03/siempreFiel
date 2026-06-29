import io
import json
import logging
import os
from datetime import date
import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from app.auth import get_current_user, require_not_veterano, flash
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
from app.database import get_db
from app.models import Familia, Perro, EstadoPerro, Voluntario, PerfilVoluntario
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/familias", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])


def _voluntarios_activos(db):
    return db.query(Voluntario).filter(Voluntario.activo == True).order_by(Voluntario.nombre).all()


def _campos_faltantes_contrato(familia, perro) -> list[str]:
    campos = []
    if not familia.email:        campos.append("Email de la familia")
    if not familia.telefono:     campos.append("Teléfono de la familia")
    if not familia.direccion:    campos.append("Dirección de la familia")
    if not familia.municipio:    campos.append("Municipio de la familia")
    if not familia.provincia:    campos.append("Provincia de la familia")
    if not familia.codigo_postal: campos.append("Código postal de la familia")
    if not perro.num_chip:       campos.append(f"Microchip de {perro.nombre}")
    if not perro.num_pasaporte:  campos.append(f"Nº pasaporte de {perro.nombre}")
    if not perro.raza:           campos.append(f"Raza de {perro.nombre}")
    if not perro.sexo:           campos.append(f"Sexo de {perro.nombre}")
    if not perro.fecha_nacimiento: campos.append(f"Fecha de nacimiento de {perro.nombre}")
    if not perro.color:          campos.append(f"Capa/color de {perro.nombre}")
    if not perro.tamano:         campos.append(f"Tamaño de {perro.nombre}")
    if perro.tasa is None:       campos.append(f"Tasa de adopción de {perro.nombre}")
    return campos


def _campos_faltantes_contrato_preadopcion(familia, perro) -> list[str]:
    campos = []
    if not familia.email:        campos.append("Email de la familia")
    if not familia.telefono:     campos.append("Teléfono de la familia")
    if not familia.direccion:    campos.append("Dirección de la familia")
    if not familia.municipio:    campos.append("Municipio de la familia")
    if not familia.provincia:    campos.append("Provincia de la familia")
    if not familia.codigo_postal: campos.append("Código postal de la familia")
    if not perro.num_chip:       campos.append(f"Microchip de {perro.nombre}")
    if not perro.raza:           campos.append(f"Raza de {perro.nombre}")
    if not perro.sexo:           campos.append(f"Sexo de {perro.nombre}")
    if not perro.fecha_nacimiento: campos.append(f"Fecha de nacimiento de {perro.nombre}")
    if not perro.color:          campos.append(f"Capa/color de {perro.nombre}")
    if not perro.tamano:         campos.append(f"Tamaño de {perro.nombre}")
    return campos


def _campos_faltantes_contrato_acogida(familia, perro) -> list[str]:
    campos = []
    if not familia.email:        campos.append("Email de la familia")
    if not familia.telefono:     campos.append("Teléfono de la familia")
    if not familia.direccion:    campos.append("Dirección de la familia")
    if not familia.municipio:    campos.append("Municipio de la familia")
    if not familia.provincia:    campos.append("Provincia de la familia")
    if not familia.codigo_postal: campos.append("Código postal de la familia")
    if not perro.num_chip:       campos.append(f"Microchip de {perro.nombre}")
    if not perro.raza:           campos.append(f"Raza de {perro.nombre}")
    if not perro.sexo:           campos.append(f"Sexo de {perro.nombre}")
    if not perro.fecha_nacimiento: campos.append(f"Fecha de nacimiento de {perro.nombre}")
    if not perro.color:          campos.append(f"Capa/color de {perro.nombre}")
    if not perro.tamano:         campos.append(f"Tamaño de {perro.nombre}")
    return campos

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


@router.get("/contratos")
def contratos_familias(request: Request, db: Session = Depends(get_db)):
    familias = db.query(Familia).order_by(Familia.apellidos.asc(), Familia.nombre.asc()).all()
    return templates.TemplateResponse(request, "familias/contratos.html", {
        "familias": familias,
        "tipo_labels": TIPO_LABELS,
        "tipo_colors": TIPO_COLORS,
    })


@router.get("/nueva")
def nueva_familia_form(request: Request, db: Session = Depends(get_db)):
    perros = db.query(Perro).filter(Perro.estado.notin_([EstadoPerro.fallecido, EstadoPerro.adoptado])).order_by(Perro.nombre).all()
    tasas_perros = {p.id: p.tasa for p in perros}
    return templates.TemplateResponse(request, "familias/form.html", {
        "familia": None,
        "perros": perros,
        "tasas_perros": tasas_perros,
        "tipo_labels": TIPO_LABELS,
        "hoy": date.today().isoformat(),
        "voluntarios": _voluntarios_activos(db),
    })


@router.post("/nueva")
def crear_familia(
    request: Request,
    nombre: str = Form(...),
    apellidos: str = Form(...),
    dni: str = Form(...),
    tipo: Optional[str] = Form(None),
    perro_id: Optional[int] = Form(None),
    tasa_perro: Optional[float] = Form(None),
    email: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    direccion: Optional[str] = Form(None),
    municipio: Optional[str] = Form(None),
    provincia: Optional[str] = Form(None),
    codigo_postal: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    fecha_contrato: date = Form(...),
    voluntario_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    familia = Familia(
        nombre=nombre.strip(),
        apellidos=apellidos.strip(),
        dni=dni.strip().upper(),
        tipo=tipo or None,
        email=email or None,
        telefono=telefono or None,
        direccion=direccion or None,
        municipio=municipio or None,
        provincia=provincia or None,
        codigo_postal=codigo_postal or None,
        notas=notas or None,
        fecha_contrato=fecha_contrato,
        voluntario_id=voluntario_id or None,
    )
    db.add(familia)
    try:
        db.flush()
        if perro_id:
            perro = db.query(Perro).filter(Perro.id == perro_id).first()
            if perro:
                perro.familia_id = familia.id
                if tasa_perro is not None:
                    perro.tasa = tasa_perro
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "Ya existe una familia con ese DNI.", "danger")
        perros = db.query(Perro).filter(Perro.estado.notin_([EstadoPerro.fallecido, EstadoPerro.adoptado])).order_by(Perro.nombre).all()
        return templates.TemplateResponse(request, "familias/form.html", {
            "familia": None,
            "perros": perros,
            "tasas_perros": {p.id: p.tasa for p in perros},
            "tipo_labels": TIPO_LABELS,
            "hoy": fecha_contrato.isoformat(),
            "voluntarios": _voluntarios_activos(db),
        })
    return RedirectResponse(f"/familias/{familia.id}", status_code=303)


@router.get("/{familia_id}")
def detalle_familia(request: Request, familia_id: int, db: Session = Depends(get_db)):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if not familia:
        return RedirectResponse("/familias/", status_code=303)
    perros_disponibles = db.query(Perro).filter(
        Perro.familia_id.is_(None),
        Perro.estado != EstadoPerro.fallecido,
    ).order_by(Perro.nombre).all()
    campos_faltantes = {
        p.id: _campos_faltantes_contrato(familia, p)
        for p in familia.perros
    }
    campos_faltantes_acogida = {
        p.id: _campos_faltantes_contrato_acogida(familia, p)
        for p in familia.perros
    }
    campos_faltantes_preadopcion = {
        p.id: _campos_faltantes_contrato_preadopcion(familia, p)
        for p in familia.perros
    }
    return templates.TemplateResponse(request, "familias/detail.html", {
        "familia": familia,
        "tipo_labels": TIPO_LABELS,
        "tipo_colors": TIPO_COLORS,
        "perros_disponibles": perros_disponibles,
        "campos_faltantes_json": json.dumps(campos_faltantes),
        "campos_faltantes_acogida_json": json.dumps(campos_faltantes_acogida),
        "campos_faltantes_preadopcion_json": json.dumps(campos_faltantes_preadopcion),
    })


@router.post("/{familia_id}/vincular-perro")
def vincular_perro(
    request: Request,
    familia_id: int,
    perro_id: int = Form(...),
    db: Session = Depends(get_db),
):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if not familia:
        return RedirectResponse("/familias/", status_code=303)
    perro = db.query(Perro).filter(
        Perro.id == perro_id,
        Perro.familia_id.is_(None),
        Perro.estado != EstadoPerro.fallecido,
    ).first()
    if perro:
        perro.familia_id = familia_id
        db.commit()
        flash(request, f"{perro.nombre} vinculado a la familia.")
    return RedirectResponse(f"/familias/{familia_id}", status_code=303)


@router.get("/{familia_id}/editar")
def editar_familia_form(request: Request, familia_id: int, db: Session = Depends(get_db)):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if not familia:
        return RedirectResponse("/familias/", status_code=303)
    perros = db.query(Perro).filter(Perro.estado.notin_([EstadoPerro.fallecido, EstadoPerro.adoptado])).order_by(Perro.nombre).all()
    return templates.TemplateResponse(request, "familias/form.html", {
        "familia": familia,
        "tipo_labels": TIPO_LABELS,
        "hoy": date.today().isoformat(),
        "voluntarios": _voluntarios_activos(db),
        "perros": perros,
        "tasas_perros": {p.id: p.tasa for p in perros},
    })


@router.post("/{familia_id}/editar")
def editar_familia(
    request: Request,
    familia_id: int,
    nombre: str = Form(...),
    apellidos: str = Form(...),
    dni: str = Form(...),
    tipo: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    direccion: Optional[str] = Form(None),
    municipio: Optional[str] = Form(None),
    provincia: Optional[str] = Form(None),
    codigo_postal: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    fecha_contrato: date = Form(...),
    voluntario_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    if not familia:
        return RedirectResponse("/familias/", status_code=303)
    familia.nombre = nombre.strip()
    familia.apellidos = apellidos.strip()
    familia.dni = dni.strip().upper()
    familia.tipo = tipo or None
    familia.email = email or None
    familia.telefono = telefono or None
    familia.direccion = direccion or None
    familia.municipio = municipio or None
    familia.provincia = provincia or None
    familia.codigo_postal = codigo_postal or None
    familia.notas = notas or None
    familia.fecha_contrato = fecha_contrato
    familia.voluntario_id = voluntario_id or None
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


@router.get("/{familia_id}/contrato-adopcion/{perro_id}")
def generar_contrato_adopcion(familia_id: int, perro_id: int, db: Session = Depends(get_db)):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    perro = db.query(Perro).filter(Perro.id == perro_id, Perro.familia_id == familia_id).first()
    if not familia or not perro:
        return RedirectResponse(f"/familias/{familia_id}", status_code=303)
    from app.utils.contrato_adopcion import generar_contrato_adopcion as _gen
    try:
        pdf_bytes, docx_bytes = _gen(familia, perro)
    except Exception as e:
        logger.error("Error generando contrato adopción familia %s: %s", familia_id, e)
        return RedirectResponse(f"/familias/{familia_id}", status_code=303)
    nombre_base = f"contrato_adopcion_{familia.apellidos.replace(' ', '_')}"
    if pdf_bytes:
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{nombre_base}.pdf"'},
        )
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nombre_base}.docx"'},
    )


@router.get("/{familia_id}/contrato-preadopcion/{perro_id}")
def generar_contrato_preadopcion(familia_id: int, perro_id: int, db: Session = Depends(get_db)):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    perro = db.query(Perro).filter(Perro.id == perro_id, Perro.familia_id == familia_id).first()
    if not familia or not perro:
        return RedirectResponse(f"/familias/{familia_id}", status_code=303)
    from app.utils.contrato_preadopcion import generar_contrato_preadopcion as _gen
    try:
        pdf_bytes, docx_bytes = _gen(familia, perro)
    except Exception as e:
        logger.error("Error generando contrato preadopción familia %s: %s", familia_id, e)
        return RedirectResponse(f"/familias/{familia_id}", status_code=303)
    nombre_base = f"contrato_preadopcion_{familia.apellidos.replace(' ', '_')}"
    if pdf_bytes:
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{nombre_base}.pdf"'},
        )
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nombre_base}.docx"'},
    )


@router.get("/{familia_id}/contrato-acogida/{perro_id}")
def generar_contrato_acogida(familia_id: int, perro_id: int, db: Session = Depends(get_db)):
    familia = db.query(Familia).filter(Familia.id == familia_id).first()
    perro = db.query(Perro).filter(Perro.id == perro_id, Perro.familia_id == familia_id).first()
    if not familia or not perro:
        return RedirectResponse(f"/familias/{familia_id}", status_code=303)
    from app.utils.contrato_acogida import generar_contrato_acogida as _gen
    try:
        pdf_bytes, docx_bytes = _gen(familia, perro)
    except Exception as e:
        logger.error("Error generando contrato acogida familia %s: %s", familia_id, e)
        return RedirectResponse(f"/familias/{familia_id}", status_code=303)
    nombre_base = f"contrato_acogida_{familia.apellidos.replace(' ', '_')}"
    if pdf_bytes:
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{nombre_base}.pdf"'},
        )
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nombre_base}.docx"'},
    )


_MAX_CONTRATO_BYTES = 10 * 1024 * 1024  # 10 MB


def _subir_contrato_familia(file: UploadFile, familia_id: int) -> tuple:
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    )
    contents = file.file.read(_MAX_CONTRATO_BYTES + 1)
    if len(contents) > _MAX_CONTRATO_BYTES:
        raise ValueError("El archivo supera el tamaño máximo permitido (10 MB).")
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
