from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import Usuario, RolUsuario, Voluntario, PerfilVoluntario, SesionUsuario
from app.auth import get_current_user, require_admin, hash_password, flash
from app.templates_config import templates

SESSION_MAX_AGE = timedelta(hours=8)


def _fmt_duracion(td: timedelta) -> str:
    total = int(td.total_seconds())
    if total < 0:
        total = 0
    h, rem = divmod(total, 3600)
    m = rem // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def _parsear_ua(ua: str) -> dict:
    ua = ua or ""
    ul = ua.lower()

    es_movil = any(t in ul for t in ("mobile", "android", "iphone", "ipad", "ipod"))

    if "edg/" in ul or "edga/" in ul:
        navegador = "Edge"
        icono = "bi-browser-edge"
    elif "firefox/" in ul:
        navegador = "Firefox"
        icono = "bi-browser-firefox"
    elif "opr/" in ul or "opera/" in ul:
        navegador = "Opera"
        icono = "bi-browser-opera"
    elif "chrome/" in ul and "chromium" not in ul:
        navegador = "Chrome"
        icono = "bi-browser-chrome"
    elif "safari/" in ul:
        navegador = "Safari"
        icono = "bi-browser-safari"
    elif ua:
        navegador = "Otro"
        icono = "bi-globe"
    else:
        return {"dispositivo_icono": "bi-question-circle", "dispositivo_label": "—", "navegador": "—", "navegador_icono": "bi-globe"}

    return {
        "dispositivo_icono": "bi-phone" if es_movil else "bi-laptop",
        "dispositivo_label": "Móvil" if es_movil else "Escritorio",
        "navegador": navegador,
        "navegador_icono": icono,
    }

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


@router.post("/{usuario_id}/eliminar")
def eliminar_usuario(
    request: Request,
    usuario_id: int,
    current_user: Usuario = Depends(require_admin),
    db: Session = Depends(get_db),
):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario or usuario.id == current_user.id:
        return RedirectResponse("/usuarios/", status_code=303)
    nombre = usuario.nombre
    db.delete(usuario)
    db.commit()
    flash(request, f"Usuario {nombre} eliminado.", "warning")
    return RedirectResponse("/usuarios/", status_code=303)


@router.get("/sesiones")
def listar_sesiones(
    request: Request,
    current_user: Usuario = Depends(require_admin),
    db: Session = Depends(get_db),
):
    sesiones_raw = (
        db.query(SesionUsuario)
        .order_by(SesionUsuario.fecha_inicio.desc())
        .limit(200)
        .all()
    )
    ahora = datetime.utcnow()
    sesiones = []
    activas = 0
    for s in sesiones_raw:
        if s.fecha_fin:
            estado = "cerrada"
            duracion = _fmt_duracion(s.fecha_fin - s.fecha_inicio)
        elif ahora - s.fecha_inicio > SESSION_MAX_AGE:
            estado = "expirada"
            duracion = _fmt_duracion(SESSION_MAX_AGE)
        else:
            estado = "activa"
            duracion = _fmt_duracion(ahora - s.fecha_inicio)
            activas += 1
        ua_info = _parsear_ua(s.user_agent or "")
        sesiones.append({
            "id": s.id,
            "usuario": s.usuario,
            "fecha_inicio": s.fecha_inicio,
            "fecha_fin": s.fecha_fin,
            "ip": s.ip or "—",
            "user_agent": s.user_agent or "",
            "estado": estado,
            "duracion": duracion,
            **ua_info,
        })
    return templates.TemplateResponse(request, "usuarios/sesiones.html", {
        "sesiones": sesiones,
        "activas": activas,
        "current_user": current_user,
        "rol_labels": ROL_LABELS,
        "rol_colors": ROL_COLORS,
    })
