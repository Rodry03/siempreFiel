from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, require_redes_access, flash
from app.database import get_db
from app.models import EstadoPerro, Perro, PerroRedes, PublicacionRedes
from app.templates_config import templates

router = APIRouter(
    prefix="/redes",
    dependencies=[Depends(get_current_user), Depends(require_redes_access)],
)

ORIGENES = ["refugio", "acogida", "otro"]
ORIGEN_LABELS = {"refugio": "Refugio", "acogida": "Acogida", "otro": "Otro"}
PLATAFORMAS = ["instagram", "tiktok"]
PLATAFORMA_LABELS = {"instagram": "Instagram", "tiktok": "TikTok"}
UBICACION_LABELS = {
    "refugio": "Refugio",
    "acogida": "Casa de acogida",
    "residencia": "Residencia canina",
    "casa_adoptiva": "Casa adoptiva",
}

VENTANA_DIAS = 90


def _perros_dropdown(db: Session):
    return (
        db.query(Perro)
        .filter(Perro.estado.in_([EstadoPerro.libre, EstadoPerro.reservado]))
        .order_by(Perro.nombre)
        .all()
    )


def _perros_json(db: Session) -> list:
    return [{"id": p.id, "nombre": p.nombre} for p in _perros_dropdown(db)]


def _ubicacion_actual(perro: Perro):
    if not perro:
        return None
    return next((u for u in perro.ubicaciones if u.fecha_fin is None), None)


def _calcular_edad(fecha_nacimiento) -> Optional[str]:
    if not fecha_nacimiento:
        return None
    hoy = date.today()
    anos = hoy.year - fecha_nacimiento.year - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
    if anos == 0:
        meses = (hoy.year - fecha_nacimiento.year) * 12 + hoy.month - fecha_nacimiento.month
        if hoy.day < fecha_nacimiento.day:
            meses -= 1
        return f"{meses} mes{'es' if meses != 1 else ''}"
    return f"{anos} año{'s' if anos != 1 else ''}"


def _stats(pr: PerroRedes, hoy: date) -> dict:
    fechas = [p.fecha for p in pr.publicaciones]
    limite = hoy - timedelta(days=VENTANA_DIAS)
    return {
        "ultima": max(fechas) if fechas else None,
        "ultimos_3_meses": sum(1 for f in fechas if f >= limite),
        "total": len(fechas),
    }


@router.get("/")
def listar(request: Request, ver: Optional[str] = None, db: Session = Depends(get_db)):
    hoy = date.today()
    mostrar_archivados = ver == "archivados"
    perros_redes = (
        db.query(PerroRedes)
        .options(joinedload(PerroRedes.publicaciones), joinedload(PerroRedes.perro))
        .filter(PerroRedes.activo == (not mostrar_archivados))
        .order_by(PerroRedes.nombre)
        .all()
    )

    filas = [{"pr": pr, **_stats(pr, hoy)} for pr in perros_redes]

    publicados = [f for f in filas if f["ultima"]]
    ultimos_publicados = sorted(publicados, key=lambda f: f["ultima"], reverse=True)[:3]

    nunca_publicados = [f for f in filas if not f["ultima"]]
    sin_publicar_hace_tiempo = (nunca_publicados + sorted(publicados, key=lambda f: f["ultima"]))[:5]

    mas_publicados = sorted(publicados, key=lambda f: f["total"], reverse=True)[:5]

    return templates.TemplateResponse(request, "redes/list.html", {
        "filas": filas,
        "ultimos_publicados": ultimos_publicados,
        "sin_publicar_hace_tiempo": sin_publicar_hace_tiempo,
        "mas_publicados": mas_publicados,
        "origen_labels": ORIGEN_LABELS,
        "mostrar_archivados": mostrar_archivados,
    })


@router.get("/nuevo")
def nuevo_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "redes/form.html", {
        "perro_redes": None,
        "perros_json": _perros_json(db),
        "origenes": ORIGENES,
        "origen_labels": ORIGEN_LABELS,
    })


@router.post("/nuevo")
def crear(
    request: Request,
    nombre: str = Form(...),
    perro_id: Optional[str] = Form(None),
    origen: str = Form(...),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    pr = PerroRedes(
        nombre=nombre.strip().upper(),
        perro_id=int(perro_id) if perro_id else None,
        origen=origen,
        notas=notas or None,
    )
    db.add(pr)
    db.commit()
    flash(request, "Perro añadido a redes.")
    return RedirectResponse(f"/redes/{pr.id}", status_code=303)


@router.post("/{pr_id}/editar")
def editar(
    pr_id: int,
    request: Request,
    nombre: str = Form(...),
    perro_id: Optional[str] = Form(None),
    origen: str = Form(...),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    pr = db.query(PerroRedes).filter(PerroRedes.id == pr_id).first()
    if pr:
        pr.nombre = nombre.strip().upper()
        pr.perro_id = int(perro_id) if perro_id else None
        pr.origen = origen
        pr.notas = notas or None
        db.commit()
        flash(request, "Datos actualizados.")
    return RedirectResponse(f"/redes/{pr_id}", status_code=303)


@router.post("/{pr_id}/archivar")
def archivar(pr_id: int, request: Request, db: Session = Depends(get_db)):
    pr = db.query(PerroRedes).filter(PerroRedes.id == pr_id).first()
    if pr:
        pr.activo = not pr.activo
        db.commit()
        flash(request, "Archivado." if not pr.activo else "Reactivado.")
    return RedirectResponse("/redes/", status_code=303)


@router.post("/{pr_id}/eliminar")
def eliminar(pr_id: int, request: Request, db: Session = Depends(get_db)):
    pr = db.query(PerroRedes).filter(PerroRedes.id == pr_id).first()
    if pr:
        db.delete(pr)
        db.commit()
        flash(request, "Eliminado.", "warning")
    return RedirectResponse("/redes/", status_code=303)


@router.get("/{pr_id}")
def detalle(pr_id: int, request: Request, db: Session = Depends(get_db)):
    pr = (
        db.query(PerroRedes)
        .options(
            joinedload(PerroRedes.publicaciones),
            joinedload(PerroRedes.perro).joinedload(Perro.raza),
            joinedload(PerroRedes.perro).joinedload(Perro.ubicaciones),
        )
        .filter(PerroRedes.id == pr_id)
        .first()
    )
    if not pr:
        return RedirectResponse("/redes/", status_code=303)
    return templates.TemplateResponse(request, "redes/detail.html", {
        "pr": pr,
        "stats": _stats(pr, date.today()),
        "plataformas": PLATAFORMAS,
        "plataforma_labels": PLATAFORMA_LABELS,
        "origenes": ORIGENES,
        "origen_labels": ORIGEN_LABELS,
        "perros_json": _perros_json(db),
        "ubicacion_actual": _ubicacion_actual(pr.perro) if pr.perro else None,
        "ubicacion_labels": UBICACION_LABELS,
        "edad": _calcular_edad(pr.perro.fecha_nacimiento) if pr.perro else None,
        "hoy": date.today().isoformat(),
    })


@router.post("/{pr_id}/publicacion")
def agregar_publicacion(
    pr_id: int,
    fecha: date = Form(...),
    plataforma: str = Form(...),
    db: Session = Depends(get_db),
):
    db.add(PublicacionRedes(perro_redes_id=pr_id, fecha=fecha, plataforma=plataforma))
    db.commit()
    return RedirectResponse(f"/redes/{pr_id}", status_code=303)


@router.post("/{pr_id}/publicacion/{pub_id}/eliminar")
def eliminar_publicacion(pr_id: int, pub_id: int, db: Session = Depends(get_db)):
    pub = db.query(PublicacionRedes).filter(
        PublicacionRedes.id == pub_id, PublicacionRedes.perro_redes_id == pr_id
    ).first()
    if pub:
        db.delete(pub)
        db.commit()
    return RedirectResponse(f"/redes/{pr_id}", status_code=303)
