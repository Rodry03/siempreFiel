from datetime import datetime
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Usuario, SesionUsuario
from app.auth import verify_password
from app.templates_config import templates

router = APIRouter()


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
    user = db.query(Usuario).filter(
        Usuario.username == username,
        Usuario.activo == True,
    ).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html",
            {"error": "Usuario o contraseña incorrectos"}, status_code=401)

    ip = request.headers.get("X-Forwarded-For", "")
    ip = ip.split(",")[0].strip() if ip else (request.client.host if request.client else None)
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


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    sesion_id = request.session.get("sesion_id")
    if sesion_id:
        sesion = db.query(SesionUsuario).filter(SesionUsuario.id == sesion_id).first()
        if sesion and sesion.fecha_fin is None:
            sesion.fecha_fin = datetime.utcnow()
            db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
