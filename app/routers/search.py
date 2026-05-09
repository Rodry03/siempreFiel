from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/buscar")
def buscar_global(q: str = Query(""), request: Request = None, db: Session = Depends(get_db)):
    q = q.strip()
    if len(q) < 2:
        return JSONResponse({"perros": [], "voluntarios": [], "visitantes": []})

    pattern = f"%{q}%"
    user = request.state.current_user
    es_veterano = user.rol.value == "veterano"

    from app.models import Perro, EstadoPerro, Voluntario, Visitante

    ESTADOS_ACTIVOS = [EstadoPerro.libre, EstadoPerro.reservado]
    perros_q = db.query(Perro).filter(Perro.nombre.ilike(pattern))
    if es_veterano:
        perros_q = perros_q.filter(Perro.estado.in_(ESTADOS_ACTIVOS))
    perros = perros_q.order_by(Perro.nombre).limit(8).all()

    result = {
        "perros": [
            {
                "id": p.id,
                "nombre": p.nombre,
                "raza": p.raza.nombre if p.raza else "—",
                "estado": p.estado.value,
            }
            for p in perros
        ],
        "voluntarios": [],
        "visitantes": [],
    }

    if not es_veterano:
        voluntarios = (
            db.query(Voluntario)
            .filter(or_(Voluntario.nombre.ilike(pattern), Voluntario.apellido.ilike(pattern)))
            .order_by(Voluntario.nombre)
            .limit(8)
            .all()
        )
        visitantes = (
            db.query(Visitante)
            .filter(or_(Visitante.nombre.ilike(pattern), Visitante.apellido.ilike(pattern)))
            .order_by(Visitante.nombre)
            .limit(8)
            .all()
        )
        result["voluntarios"] = [
            {
                "id": v.id,
                "nombre": f"{v.nombre} {v.apellido}",
                "perfil": v.perfil.value,
                "activo": v.activo,
            }
            for v in voluntarios
        ]
        result["visitantes"] = [
            {
                "id": v.id,
                "nombre": f"{v.nombre} {v.apellido}",
                "estado": v.estado.value,
            }
            for v in visitantes
        ]

    return JSONResponse(result)
