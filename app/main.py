import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from app.database import init_db
from app.routers import dashboard, perros, voluntarios, turnos, visitas, usuarios
from app.routers import login as login_router
from app.auth import NotAuthenticated, NotAuthorized, CurrentUserMiddleware

app = FastAPI(title="Siempre Fiel")

# SessionMiddleware debe ir primero (más exterior) para que CurrentUserMiddleware
# pueda leer request.session
app.add_middleware(CurrentUserMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "dev-secret-change-in-production"),
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(login_router.router)
app.include_router(dashboard.router)
app.include_router(perros.router)
app.include_router(voluntarios.router)
app.include_router(turnos.router)
app.include_router(visitas.router)
app.include_router(usuarios.router)


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(NotAuthorized)
async def not_authorized_handler(request: Request, exc: NotAuthorized):
    return RedirectResponse("/", status_code=303)


@app.on_event("startup")
def on_startup():
    init_db()
