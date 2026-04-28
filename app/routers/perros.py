import os
from datetime import date
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from app.auth import get_current_user
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, and_
from typing import Optional
from app.database import get_db
from app.models import Perro, Vacuna, Ubicacion, EstadoPerro, Sexo, TipoUbicacion, Raza
from app.templates_config import templates
import cloudinary
import cloudinary.uploader


def _subir_foto(file: UploadFile, perro_id: int) -> Optional[str]:
    if not file or not file.filename:
        return None
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    )
    contents = file.file.read()
    result = cloudinary.uploader.upload(
        contents,
        folder="protectora",
        public_id=f"perro_{perro_id}",
        overwrite=True,
        transformation=[{"width": 800, "crop": "limit"}],
    )
    return result["secure_url"]

router = APIRouter(prefix="/perros", dependencies=[Depends(get_current_user)])

UBICACION_LABELS = {
    "refugio": "Refugio",
    "acogida": "Casa de acogida",
    "residencia": "Residencia canina",
    "adoptado": "Adoptado",
}


def _ubicacion_actual(perro: Perro) -> Optional[Ubicacion]:
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


POR_PAGINA = 25

COLUMNAS_ORDEN = {
    "nombre":        Perro.nombre,
    "raza":          Raza.nombre,
    "sexo":          Perro.sexo,
    "esterilizado":  Perro.esterilizado,
    "fecha_entrada": Perro.fecha_entrada,
    "dias":          Perro.fecha_entrada,
}

@router.get("/")
def listar_perros(
    request: Request,
    estado: str = "activo",
    page: int = 1,
    sort: str = "nombre",
    order: str = "asc",
    q: str = "",
    ubicacion: str = "refugio",
    raza_id: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Perro).join(Raza)
    if estado != "todos":
        try:
            query = query.filter(Perro.estado == EstadoPerro(estado))
        except ValueError:
            pass
    if q:
        query = query.filter(Perro.nombre.ilike(f"%{q}%"))
    if ubicacion:
        query = query.join(Ubicacion, and_(
            Ubicacion.perro_id == Perro.id,
            Ubicacion.fecha_fin == None,
            Ubicacion.tipo == TipoUbicacion(ubicacion),
        ))
    if raza_id:
        query = query.filter(Perro.raza_id == raza_id)

    columna = COLUMNAS_ORDEN.get(sort, Perro.nombre)
    dir_fn = desc if order == "desc" else asc
    query = query.order_by(dir_fn(columna))

    total = query.count()
    total_paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    page = max(1, min(page, total_paginas))
    perros = query.offset((page - 1) * POR_PAGINA).limit(POR_PAGINA).all()
    hoy = date.today()
    perros_con_ubicacion = [(p, _ubicacion_actual(p), (hoy - p.fecha_entrada).days) for p in perros]
    razas = db.query(Raza).order_by(Raza.nombre).all()
    return templates.TemplateResponse(request, "perros/list.html", {
        "perros_con_ubicacion": perros_con_ubicacion,
        "estado_filtro": estado,
        "ubicacion_labels": UBICACION_LABELS,
        "page": page,
        "total_paginas": total_paginas,
        "total": total,
        "sort": sort,
        "order": order,
        "q": q,
        "ubicacion_filtro": ubicacion,
        "raza_id_filtro": raza_id,
        "razas": razas,
    })


@router.get("/nuevo")
def form_nuevo_perro(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "perros/form.html", {
        "perro": None,
        "sexos": [s.value for s in Sexo],
        "razas": db.query(Raza).order_by(Raza.nombre).all(),
        "hoy": date.today().isoformat(),
    })


@router.post("/nuevo")
def crear_perro(
    request: Request,
    nombre: str = Form(...),
    raza_id: int = Form(...),
    sexo: str = Form(...),
    esterilizado: Optional[str] = Form(None),
    ppp: Optional[str] = Form(None),
    fecha_entrada: date = Form(...),
    estado: str = Form("activo"),
    fecha_nacimiento: Optional[date] = Form(None),
    num_chip: Optional[str] = Form(None),
    num_pasaporte: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    perro = Perro(
        nombre=nombre.upper(),
        raza_id=raza_id,
        sexo=Sexo(sexo),
        esterilizado=esterilizado == "on",
        ppp=ppp == "on",
        fecha_entrada=fecha_entrada,
        estado=EstadoPerro(estado),
        fecha_nacimiento=fecha_nacimiento,
        num_chip=num_chip or None,
        num_pasaporte=num_pasaporte or None,
        color=color or None,
        notas=notas or None,
    )
    db.add(perro)
    db.flush()
    perro.foto_url = _subir_foto(foto, perro.id)
    db.add(Ubicacion(perro_id=perro.id, tipo=TipoUbicacion.refugio, fecha_inicio=fecha_entrada))
    db.commit()
    return RedirectResponse(f"/perros/{perro.id}", status_code=303)


@router.get("/{perro_id}")
def detalle_perro(request: Request, perro_id: int, db: Session = Depends(get_db)):
    perro = db.query(Perro).filter(Perro.id == perro_id).first()
    if not perro:
        return RedirectResponse("/perros/", status_code=303)
    vacunas = sorted(perro.vacunas, key=lambda v: v.fecha_administracion, reverse=True)
    return templates.TemplateResponse(request, "perros/detail.html", {
        "perro": perro,
        "vacunas": vacunas,
        "ubicacion_actual": _ubicacion_actual(perro),
        "ubicacion_labels": UBICACION_LABELS,
        "hoy": date.today().isoformat(),
        "tipos_ubicacion": [t.value for t in TipoUbicacion],
        "edad": _calcular_edad(perro.fecha_nacimiento),
    })


@router.get("/{perro_id}/editar")
def form_editar_perro(request: Request, perro_id: int, db: Session = Depends(get_db)):
    perro = db.query(Perro).filter(Perro.id == perro_id).first()
    if not perro:
        return RedirectResponse("/perros/", status_code=303)
    return templates.TemplateResponse(request, "perros/form.html", {
        "perro": perro,
        "sexos": [s.value for s in Sexo],
        "razas": db.query(Raza).order_by(Raza.nombre).all(),
        "hoy": date.today().isoformat(),
    })


@router.post("/{perro_id}/editar")
def editar_perro(
    perro_id: int,
    nombre: str = Form(...),
    raza_id: int = Form(...),
    sexo: str = Form(...),
    esterilizado: Optional[str] = Form(None),
    ppp: Optional[str] = Form(None),
    fecha_entrada: date = Form(...),
    estado: str = Form("activo"),
    fecha_nacimiento: Optional[date] = Form(None),
    num_chip: Optional[str] = Form(None),
    num_pasaporte: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    perro = db.query(Perro).filter(Perro.id == perro_id).first()
    if not perro:
        return RedirectResponse("/perros/", status_code=303)
    perro.nombre = nombre.upper()
    perro.raza_id = raza_id
    perro.sexo = Sexo(sexo)
    perro.esterilizado = esterilizado == "on"
    perro.ppp = ppp == "on"
    perro.fecha_entrada = fecha_entrada
    perro.estado = EstadoPerro(estado)
    perro.fecha_nacimiento = fecha_nacimiento
    perro.num_chip = num_chip or None
    perro.num_pasaporte = num_pasaporte or None
    perro.color = color or None
    perro.notas = notas or None
    nueva_url = _subir_foto(foto, perro_id)
    if nueva_url:
        perro.foto_url = nueva_url
    db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/eliminar")
def eliminar_perro(perro_id: int, db: Session = Depends(get_db)):
    perro = db.query(Perro).filter(Perro.id == perro_id).first()
    if perro:
        db.delete(perro)
        db.commit()
    return RedirectResponse("/perros/", status_code=303)


@router.post("/{perro_id}/vacuna")
def agregar_vacuna(
    perro_id: int,
    tipo: str = Form(...),
    fecha_administracion: date = Form(...),
    fecha_proxima: Optional[date] = Form(None),
    veterinario: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    vacuna = Vacuna(
        perro_id=perro_id,
        tipo=tipo,
        fecha_administracion=fecha_administracion,
        fecha_proxima=fecha_proxima,
        veterinario=veterinario or None,
        notas=notas or None,
    )
    db.add(vacuna)
    db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/ubicacion")
def cambiar_ubicacion(
    perro_id: int,
    tipo: str = Form(...),
    fecha_inicio: date = Form(...),
    nombre_contacto: Optional[str] = Form(None),
    telefono_contacto: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    ubicacion_actual = db.query(Ubicacion).filter(
        Ubicacion.perro_id == perro_id,
        Ubicacion.fecha_fin.is_(None)
    ).first()
    if ubicacion_actual:
        ubicacion_actual.fecha_fin = fecha_inicio

    db.add(Ubicacion(
        perro_id=perro_id,
        tipo=TipoUbicacion(tipo),
        fecha_inicio=fecha_inicio,
        nombre_contacto=nombre_contacto or None,
        telefono_contacto=telefono_contacto or None,
        notas=notas or None,
    ))
    if tipo == "adoptado":
        perro = db.query(Perro).filter(Perro.id == perro_id).first()
        if perro:
            perro.estado = EstadoPerro.adoptado
    db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)
