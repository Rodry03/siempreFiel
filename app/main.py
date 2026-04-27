from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import init_db
from app.routers import dashboard, perros, voluntarios, turnos, visitas

app = FastAPI(title="Siempre Fiel")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(dashboard.router)
app.include_router(perros.router)
app.include_router(voluntarios.router)
app.include_router(turnos.router)
app.include_router(visitas.router)


@app.on_event("startup")
def on_startup():
    init_db()
