import io
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)
from datetime import date
from docx import Document as DocxDocument
from fastapi import APIRouter, Depends, Form, Request
from app.auth import get_current_user, require_not_veterano
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
from app.database import get_db
from app.models import Voluntario, PerfilVoluntario, EstadoContrato
from app.templates_config import templates

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "contracts", "contrato_voluntario.docx")
MESES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]


def _set_cell_text(cell, text):
    para = cell.paragraphs[0]
    for run in para.runs:
        run.text = ""
    if para.runs:
        para.runs[0].text = text
    else:
        para.add_run(text)


def _set_paragraph_text(para, text):
    for run in para.runs:
        run.text = ""
    if para.runs:
        para.runs[0].text = text
    else:
        para.add_run(text)


def _docx_a_pdf(docx_path: str) -> bytes | None:
    # Intenta con docx2pdf (usa Microsoft Word en Windows)
    try:
        from docx2pdf import convert as docx2pdf_convert
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "contrato.pdf")
            docx2pdf_convert(docx_path, pdf_path)
            with open(pdf_path, "rb") as f:
                return f.read()
    except Exception:
        pass

    # Fallback: LibreOffice (Linux/Render)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "/usr/bin/soffice",
                    "--headless",
                    "-env:UserInstallation=file:///tmp/libreoffice_profile",
                    "--convert-to", "pdf",
                    "--outdir", tmpdir,
                    docx_path,
                ],
                capture_output=True, timeout=60,
            )
            logger.warning("soffice returncode: %s", result.returncode)
            logger.warning("soffice stdout: %s", result.stdout.decode(errors="replace"))
            logger.warning("soffice stderr: %s", result.stderr.decode(errors="replace"))
            if result.returncode != 0:
                return None
            base = os.path.splitext(os.path.basename(docx_path))[0]
            pdf_path = os.path.join(tmpdir, base + ".pdf")
            with open(pdf_path, "rb") as f:
                return f.read()
    except FileNotFoundError:
        logger.warning("soffice no encontrado en el sistema")
        return None

router = APIRouter(prefix="/voluntarios", dependencies=[Depends(get_current_user), Depends(require_not_veterano)])


@router.get("/debug/soffice")
def debug_soffice():
    result = subprocess.run(
        ["find", "/", "-name", "soffice", "-type", "f"],
        capture_output=True, timeout=30,
    )
    return {
        "stdout": result.stdout.decode(errors="replace"),
        "stderr": result.stderr.decode(errors="replace"),
    }

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


@router.get("/{voluntario_id}/contrato")
def generar_contrato(voluntario_id: int, db: Session = Depends(get_db)):
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if not voluntario:
        return RedirectResponse("/voluntarios/", status_code=303)

    doc = DocxDocument(TEMPLATE_PATH)
    tabla = doc.tables[0]

    hoy = date.today()
    fecha_str = f"  En Salamanca a {hoy.day} de {MESES[hoy.month - 1]} del {hoy.year}.          "

    _set_cell_text(tabla.rows[0].cells[0], f"NOMBRE Y APELLIDOS: {voluntario.nombre} {voluntario.apellido}")
    _set_cell_text(tabla.rows[1].cells[0], f"DNI: {voluntario.dni or ''}")
    _set_cell_text(tabla.rows[1].cells[1], f"CORREO ELECTRÓNICO: {voluntario.email or ''}")
    _set_cell_text(tabla.rows[2].cells[0], f"DIRECCIÓN: {voluntario.direccion or ''}")
    _set_cell_text(tabla.rows[3].cells[1], f"PROVINCIA: {voluntario.provincia or 'Salamanca'}")
    _set_cell_text(tabla.rows[4].cells[0], f"C.P: {voluntario.codigo_postal or '37004'}")
    _set_cell_text(tabla.rows[4].cells[1], f"TELÉFONO: {voluntario.telefono or ''}")

    for para in doc.paragraphs:
        if "En Salamanca a" in para.text:
            _set_paragraph_text(para, fecha_str)
            break

    docx_buf = io.BytesIO()
    doc.save(docx_buf)
    docx_bytes = docx_buf.getvalue()

    nombre = f"{voluntario.nombre}_{voluntario.apellido}"

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(docx_bytes)
        docx_path = tmp.name

    try:
        pdf_bytes = _docx_a_pdf(docx_path)
    finally:
        os.unlink(docx_path)

    if pdf_bytes:
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="Contrato_{nombre}.pdf"'},
        )

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="Contrato_{nombre}.docx"'},
    )


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
