from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.auth import get_current_user, require_directiva, flash
from app.database import get_db
from app.models import NotaGestion, Voluntario, PerfilVoluntario
from app.templates_config import templates

router = APIRouter(
    prefix="/notas",
    dependencies=[Depends(get_current_user), Depends(require_directiva)],
)

_PERFILES_DIRECTIVA = {PerfilVoluntario.directiva, PerfilVoluntario.apoyo_en_junta}


def _encargados(db: Session):
    return (
        db.query(Voluntario)
        .filter(Voluntario.activo == True, Voluntario.perfil.in_(list(_PERFILES_DIRECTIVA)))
        .order_by(Voluntario.apellido, Voluntario.nombre)
        .all()
    )


@router.get("/")
def listar_notas(request: Request, db: Session = Depends(get_db)):
    hoy = date.today()
    pendientes = (
        db.query(NotaGestion)
        .filter(NotaGestion.hecha == False)
        .order_by(NotaGestion.fecha_limite.asc().nullslast(), NotaGestion.fecha_creacion.asc())
        .all()
    )
    hechas = (
        db.query(NotaGestion)
        .filter(NotaGestion.hecha == True)
        .order_by(NotaGestion.fecha_limite.desc().nullsfirst(), NotaGestion.fecha_creacion.desc())
        .all()
    )
    return templates.TemplateResponse(request, "notas/list.html", {
        "pendientes": pendientes,
        "hechas": hechas,
        "encargados": _encargados(db),
        "hoy": hoy,
    })


@router.post("/nueva")
def crear_nota(
    request: Request,
    texto: str = Form(...),
    fecha_limite: Optional[date] = Form(None),
    encargado_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    db.add(NotaGestion(
        texto=texto,
        fecha_limite=fecha_limite,
        encargado_id=encargado_id or None,
    ))
    db.commit()
    return RedirectResponse("/notas/", status_code=303)


@router.post("/{nota_id}/completar")
def completar_nota(nota_id: int, db: Session = Depends(get_db)):
    nota = db.query(NotaGestion).filter(NotaGestion.id == nota_id).first()
    if nota:
        nota.hecha = not nota.hecha
        db.commit()
    return RedirectResponse("/notas/", status_code=303)


@router.post("/{nota_id}/eliminar")
def eliminar_nota(request: Request, nota_id: int, db: Session = Depends(get_db)):
    nota = db.query(NotaGestion).filter(NotaGestion.id == nota_id).first()
    if nota:
        db.delete(nota)
        db.commit()
    return RedirectResponse("/notas/", status_code=303)
