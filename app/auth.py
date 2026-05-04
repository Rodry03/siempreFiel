from passlib.context import CryptContext
from fastapi import Depends, Request
from typing import Optional

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class NotAuthenticated(Exception):
    pass


class NotAuthorized(Exception):
    pass


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_current_user(request: Request):
    user = getattr(request.state, "current_user", None)
    if not user:
        raise NotAuthenticated()
    return user


def require_admin(request: Request):
    user = getattr(request.state, "current_user", None)
    if not user:
        raise NotAuthenticated()
    from app.models import RolUsuario
    if user.rol != RolUsuario.admin:
        raise NotAuthorized()
    return user


def require_not_veterano(request: Request):
    user = getattr(request.state, "current_user", None)
    if not user:
        raise NotAuthenticated()
    from app.models import RolUsuario
    if user.rol == RolUsuario.veterano:
        raise NotAuthorized()
    return user


def require_directiva(request: Request):
    user = getattr(request.state, "current_user", None)
    if not user:
        raise NotAuthenticated()
    from app.models import RolUsuario, PerfilVoluntario
    if user.rol == RolUsuario.admin:
        return user
    if user.voluntario and user.voluntario.perfil in (
        PerfilVoluntario.directiva, PerfilVoluntario.apoyo_en_junta
    ):
        return user
    raise NotAuthorized()


def flash(request: Request, message: str, category: str = "success") -> None:
    msgs = request.session.get("_flash", [])
    msgs.append({"category": category, "message": message})
    request.session["_flash"] = msgs


class CurrentUserMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            state = scope.setdefault("state", {})
            state["current_user"] = None
            session = scope.get("session", {})
            user_id = session.get("user_id")
            if user_id:
                from app.database import SessionLocal
                from app.models import Usuario
                from sqlalchemy.orm import joinedload
                db = SessionLocal()
                try:
                    user = db.query(Usuario).options(
                        joinedload(Usuario.voluntario)
                    ).filter(
                        Usuario.id == user_id,
                        Usuario.activo == True,
                    ).first()
                    state["current_user"] = user
                except Exception:
                    pass
                finally:
                    db.close()
        await self.app(scope, receive, send)
