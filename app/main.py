import os
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from app.templates_config import templates
from app.database import init_db
from app.routers import dashboard, perros, voluntarios, turnos, turnos_admin, visitas, usuarios, tareas, notas, instalaciones, search, eventos, economia, familias, consulta
from app.routers import login as login_router
from app.auth import NotAuthenticated, NotAuthorized, CurrentUserMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(title="Siempre Fiel")

_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    import sys
    if "pytest" not in sys.modules:
        raise RuntimeError("SECRET_KEY no está configurada. Genera una con: python -c \"import secrets; print(secrets.token_hex(32))\"")
    _secret_key = "test-only-secret"

# SessionMiddleware debe ir primero (más exterior) para que CurrentUserMiddleware
# pueda leer request.session
app.add_middleware(CurrentUserMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret_key,
    https_only=os.getenv("ENVIRONMENT") == "production",
    same_site="lax",
    max_age=8 * 3600,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(login_router.router)
app.include_router(dashboard.router)
app.include_router(perros.router)
app.include_router(voluntarios.router)
app.include_router(turnos.router)
app.include_router(turnos_admin.router)
app.include_router(visitas.router)
app.include_router(usuarios.router)
app.include_router(tareas.router)
app.include_router(notas.router)
app.include_router(instalaciones.router)
app.include_router(search.router)
app.include_router(eventos.router)
app.include_router(economia.router)
app.include_router(familias.router)
app.include_router(consulta.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    if exc.status_code == 500:
        return templates.TemplateResponse(request, "500.html", {}, status_code=500)
    from fastapi.exception_handlers import http_exception_handler as _default
    return await _default(request, exc)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Error no controlado en %s %s", request.method, request.url)
    return templates.TemplateResponse(request, "500.html", {}, status_code=500)


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(NotAuthorized)
async def not_authorized_handler(request: Request, exc: NotAuthorized):
    return RedirectResponse("/perros/", status_code=303)


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return Response(status_code=200)


@app.on_event("startup")
def on_startup():
    init_db()
