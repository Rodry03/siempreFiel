from passlib.context import CryptContext
from fastapi import Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware

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


class CurrentUserMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from app.database import SessionLocal
        from app.models import Usuario
        request.state.current_user = None
        user_id = request.session.get("user_id")
        if user_id:
            db = SessionLocal()
            try:
                user = db.query(Usuario).filter(
                    Usuario.id == user_id,
                    Usuario.activo == True,
                ).first()
                request.state.current_user = user
            finally:
                db.close()
        return await call_next(request)
