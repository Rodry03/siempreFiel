from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Usuario, RolUsuario, Voluntario, PerfilVoluntario
from app.auth import get_current_user, require_admin, hash_password, flash
from app.templates_config import templates

router = APIRouter(prefix="/usuarios")

ROL_LABELS = {"admin": "Admin", "junta": "Junta", "veterano": "Veterano"}
ROL_COLORS = {"admin": "danger", "junta": "primary", "veterano": "warning"}


def _contexto(db, extra={}):
    voluntarios = db.query(Voluntario).filter(
        Voluntario.activo == True,
        Voluntario.perfil != PerfilVoluntario.voluntario,
    ).order_by(Voluntario.apellido, Voluntario.nombre).all()
    return {
        "roles": [r.value for r in RolUsuario],
        "rol_labels": ROL_LABELS,
        "rol_colors": ROL_COLORS,
        "voluntarios": voluntarios,
        **extra,
    }


@router.get("/")
def listar_usuarios(
    request: Request,
    current_user: Usuario = Depends(require_admin),
    db: Session = Depends(get_db),
):
    usuarios = db.query(Usuario).order_by(Usuario.nombre).all()
    return templates.TemplateResponse(request, "usuarios/list.html", _contexto(db, {
        "usuarios": usuarios,
        "current_user": current_user,
    }))


@router.get("/nuevo")
def form_nuevo_usuario(
    request: Request,
    current_user: Usuario = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(request, "usuarios/form.html", _contexto(db, {
        "usuario": None,
        "current_user": current_user,
    }))


@router.post("/nuevo")
def crear_usuario(
    request: Request,
    nombre: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    rol: str = Form(...),
    activo: Optional[str] = Form(None),
    voluntario_id: Optional[int] = Form(None),
    current_user: Usuario = Depends(require_admin),
    db: Session = Depends(get_db),
):
    usuario = Usuario(
        nombre=nombre,
        username=username,
        password_hash=hash_password(password),
        rol=RolUsuario(rol),
        activo=activo == "on",
        voluntario_id=voluntario_id or None,
    )
    db.add(usuario)
    try:
        db.commit()
    except Exception:
        db.rollback()
        return templates.TemplateResponse(request, "usuarios/form.html", _contexto(db, {
            "usuario": usuario,
            "current_user": current_user,
            "error": "El nombre de usuario ya existe.",
        }))
    flash(request, f"Usuario {usuario.nombre} creado correctamente.")
    return RedirectResponse("/usuarios/", status_code=303)


@router.get("/{usuario_id}/editar")
def form_editar_usuario(
    request: Request,
    usuario_id: int,
    current_user: Usuario = Depends(require_admin),
    db: Session = Depends(get_db),
):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        return RedirectResponse("/usuarios/", status_code=303)
    return templates.TemplateResponse(request, "usuarios/form.html", _contexto(db, {
        "usuario": usuario,
        "current_user": current_user,
    }))


@router.post("/{usuario_id}/editar")
def editar_usuario(
    request: Request,
    usuario_id: int,
    nombre: str = Form(...),
    username: str = Form(...),
    password: Optional[str] = Form(None),
    rol: str = Form(...),
    activo: Optional[str] = Form(None),
    voluntario_id: Optional[int] = Form(None),
    current_user: Usuario = Depends(require_admin),
    db: Session = Depends(get_db),
):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        return RedirectResponse("/usuarios/", status_code=303)
    usuario.nombre = nombre
    usuario.username = username
    usuario.rol = RolUsuario(rol)
    usuario.activo = activo == "on"
    usuario.voluntario_id = voluntario_id or None
    if password:
        usuario.password_hash = hash_password(password)
    try:
        db.commit()
    except Exception:
        db.rollback()
        return templates.TemplateResponse(request, "usuarios/form.html", _contexto(db, {
            "usuario": usuario,
            "current_user": current_user,
            "error": "El nombre de usuario ya existe.",
        }))
    flash(request, "Cambios guardados.")
    return RedirectResponse("/usuarios/", status_code=303)
