from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import init_db
from app.routers import dashboard, perros, voluntarios, turnos

app = FastAPI(title="Protectora de Perros")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(dashboard.router)
app.include_router(perros.router)
app.include_router(voluntarios.router)
app.include_router(turnos.router)


@app.on_event("startup")
def on_startup():
    init_db()
