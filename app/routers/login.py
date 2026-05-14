from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Usuario, SesionUsuario
from app.auth import verify_password
from app.templates_config import templates

router = APIRouter()

_MAX_INTENTOS = 5
_BLOQUEO = timedelta(minutes=15)
# {ip: {"intentos": int, "desde": datetime}}
_intentos: dict = defaultdict(lambda: {"intentos": 0, "desde": datetime.utcnow()})


def _ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


def _bloqueado(ip: str) -> bool:
    estado = _intentos[ip]
    if estado["intentos"] < _MAX_INTENTOS:
        return False
    if datetime.utcnow() - estado["desde"] > _BLOQUEO:
        del _intentos[ip]
        return False
    return True


def _registrar_fallo(ip: str) -> None:
    estado = _intentos[ip]
    if datetime.utcnow() - estado["desde"] > _BLOQUEO:
        _intentos[ip] = {"intentos": 1, "desde": datetime.utcnow()}
    else:
        estado["intentos"] += 1


def _limpiar_intentos(ip: str) -> None:
    _intentos.pop(ip, None)


@router.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = _ip(request)
    if _bloqueado(ip):
        return templates.TemplateResponse(request, "login.html",
            {"error": "Demasiados intentos fallidos. Espera 15 minutos."}, status_code=429)

    user = db.query(Usuario).filter(
        Usuario.username == username,
        Usuario.activo == True,
    ).first()
    if not user or not verify_password(password, user.password_hash):
        _registrar_fallo(ip)
        return templates.TemplateResponse(request, "login.html",
            {"error": "Usuario o contraseña incorrectos"}, status_code=401)

    _limpiar_intentos(ip)
    sesion = SesionUsuario(
        usuario_id=user.id,
        ip=ip,
        user_agent=request.headers.get("User-Agent", "")[:500],
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)

    request.session["user_id"] = user.id
    request.session["sesion_id"] = sesion.id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    sesion_id = request.session.get("sesion_id")
    if sesion_id:
        sesion = db.query(SesionUsuario).filter(SesionUsuario.id == sesion_id).first()
        if sesion and sesion.fecha_fin is None:
            sesion.fecha_fin = datetime.utcnow()
            db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
