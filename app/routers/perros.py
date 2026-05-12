import os
from datetime import date, timedelta
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from app.auth import get_current_user, require_not_veterano, flash
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, and_, or_
from typing import List, Optional
from app.database import get_db
from app.models import Perro, Vacuna, Ubicacion, EstadoPerro, Sexo, TipoUbicacion, Raza, PesoPerro, CeloPerro, MedicacionPerro
from app.templates_config import templates
import cloudinary
import cloudinary.uploader


_MAX_FOTO_BYTES = 8 * 1024 * 1024  # 8 MB


def _subir_foto(file: UploadFile, perro_id: int) -> Optional[str]:
    if not file or not file.filename:
        return None
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    )
    contents = file.file.read(_MAX_FOTO_BYTES + 1)
    if len(contents) > _MAX_FOTO_BYTES:
        return None
    result = cloudinary.uploader.upload(
        contents,
        folder="protectora",
        public_id=f"perro_{perro_id}",
        overwrite=True,
        transformation=[{"width": 800, "crop": "limit"}],
    )
    return result["secure_url"]

router = APIRouter(prefix="/perros", dependencies=[Depends(get_current_user)])

TIPOS_VACUNA = [
    "Rabia",
    "Canigen",
    "DPT (Difteria, Pertussis, Tetanos)",
    "Leptospirosis",
    "Leishmaniasis",
    "Tos de las perreras (Bordetella)",
    "Parvovirosis",
    "Moquillo",
    "Hepatitis",
    "Coronavirus",
    "Desparasitación Interna",
    "Otra",
]

UBICACION_LABELS = {
    "refugio": "Refugio",
    "acogida": "Casa de acogida",
    "residencia": "Residencia canina",
    "casa_adoptiva": "Casa adoptiva",
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


POR_PAGINA = 35

COLUMNAS_ORDEN = {
    "nombre":        Perro.nombre,
    "raza":          Raza.nombre,
    "sexo":          Perro.sexo,
    "esterilizado":  Perro.esterilizado,
    "fecha_entrada": Perro.fecha_entrada,
    "dias":          Perro.fecha_entrada,
}

def _auto_adoptar_reservados(db: Session) -> None:
    """Adopta automáticamente perros reservados hace más de 30 días."""
    limite = date.today() - timedelta(days=30)
    reservados = (
        db.query(Perro)
        .filter(
            Perro.estado == EstadoPerro.reservado,
            Perro.fecha_reserva.isnot(None),
            Perro.fecha_reserva <= limite,
        )
        .all()
    )
    if not reservados:
        return
    hoy = date.today()
    for perro in reservados:
        perro.estado = EstadoPerro.adoptado
        if not perro.fecha_adopcion:
            perro.fecha_adopcion = hoy
        perro.fecha_reserva = None
        ub_actual = _ubicacion_actual(perro)
        if ub_actual and ub_actual.tipo != TipoUbicacion.casa_adoptiva:
            ub_actual.fecha_fin = hoy
            db.add(Ubicacion(perro_id=perro.id, tipo=TipoUbicacion.casa_adoptiva, fecha_inicio=hoy))
        elif ub_actual is None:
            db.add(Ubicacion(perro_id=perro.id, tipo=TipoUbicacion.casa_adoptiva, fecha_inicio=hoy))
    db.commit()


@router.get("/")
def listar_perros(
    request: Request,
    estado: str = "activos",
    page: int = 1,
    sort: str = "nombre",
    order: str = "asc",
    q: str = "",
    ubicacion: str = "refugio",
    raza_id: int = 0,
    db: Session = Depends(get_db),
):
    from app.models import RolUsuario
    if request.state.current_user and request.state.current_user.rol == RolUsuario.veterano:
        estado = "activos"
        ubicacion = "refugio"
    else:
        _auto_adoptar_reservados(db)

    query = db.query(Perro).join(Raza)
    ESTADOS_ACTIVOS = [EstadoPerro.libre, EstadoPerro.reservado]
    if estado == "activos":
        query = query.filter(Perro.estado.in_(ESTADOS_ACTIVOS))
    elif estado != "todos":
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

    if sort == "peso":
        peso_sq = (
            db.query(PesoPerro.perro_id, PesoPerro.peso_kg)
            .distinct(PesoPerro.perro_id)
            .order_by(PesoPerro.perro_id, PesoPerro.fecha.desc())
            .subquery("ultimo_peso")
        )
        query = query.outerjoin(peso_sq, peso_sq.c.perro_id == Perro.id)
        columna = peso_sq.c.peso_kg
    else:
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

    medicaciones_hoy = []
    if ubicacion == "refugio":
        medicaciones_hoy = (
            db.query(MedicacionPerro)
            .join(Perro, MedicacionPerro.perro_id == Perro.id)
            .join(Ubicacion, and_(
                Ubicacion.perro_id == Perro.id,
                Ubicacion.fecha_fin == None,
                Ubicacion.tipo == TipoUbicacion.refugio,
            ))
            .filter(
                Perro.estado.in_([EstadoPerro.libre, EstadoPerro.reservado]),
                MedicacionPerro.fecha_inicio <= hoy,
                or_(MedicacionPerro.fecha_fin == None, MedicacionPerro.fecha_fin >= hoy),
            )
            .order_by(Perro.nombre, MedicacionPerro.medicamento)
            .all()
        )

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
        "medicaciones_hoy": medicaciones_hoy,
        "hoy": hoy,
    })


@router.get("/nuevo")
def form_nuevo_perro(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "perros/form.html", {
        "perro": None,
        "sexos": [s.value for s in Sexo],
        "razas": db.query(Raza).order_by(Raza.nombre).all(),
        "hoy": date.today().isoformat(),
        "tipos_ubicacion": [t.value for t in TipoUbicacion],
        "ubicacion_labels": UBICACION_LABELS,
    })


@router.post("/nuevo", dependencies=[Depends(require_not_veterano)])
def crear_perro(
    request: Request,
    nombre: str = Form(...),
    raza_id: int = Form(...),
    sexo: str = Form(...),
    esterilizado: Optional[str] = Form(None),
    ppp: Optional[str] = Form(None),
    fecha_entrada: date = Form(...),
    estado: str = Form("libre"),
    fecha_nacimiento: Optional[date] = Form(None),
    fecha_adopcion: Optional[date] = Form(None),
    num_chip: Optional[str] = Form(None),
    num_pasaporte: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    ubicacion_tipo: str = Form("refugio"),
    nombre_contacto_ub: Optional[str] = Form(None),
    telefono_contacto_ub: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    tipo_ub = TipoUbicacion(ubicacion_tipo)
    estado_efectivo = EstadoPerro.adoptado if tipo_ub == TipoUbicacion.casa_adoptiva else EstadoPerro(estado)
    fecha_adopcion_efectiva = fecha_adopcion if estado_efectivo == EstadoPerro.adoptado else None

    perro = Perro(
        nombre=nombre.upper(),
        raza_id=raza_id,
        sexo=Sexo(sexo),
        esterilizado=esterilizado == "on",
        ppp=ppp == "on",
        fecha_entrada=fecha_entrada,
        estado=estado_efectivo,
        fecha_adopcion=fecha_adopcion_efectiva or (fecha_entrada if estado_efectivo == EstadoPerro.adoptado else None),
        fecha_reserva=fecha_entrada if estado_efectivo == EstadoPerro.reservado else None,
        fecha_nacimiento=fecha_nacimiento,
        num_chip=num_chip or None,
        num_pasaporte=num_pasaporte or None,
        color=color or None,
        notas=notas or None,
    )
    db.add(perro)
    db.flush()
    perro.foto_url = _subir_foto(foto, perro.id)
    db.add(Ubicacion(
        perro_id=perro.id,
        tipo=tipo_ub,
        fecha_inicio=fecha_entrada,
        nombre_contacto=nombre_contacto_ub or None,
        telefono_contacto=telefono_contacto_ub or None,
    ))
    db.commit()
    flash(request, f"Perro {perro.nombre} creado correctamente.")
    return RedirectResponse(f"/perros/{perro.id}", status_code=303)


@router.get("/{perro_id}")
def detalle_perro(request: Request, perro_id: int, error: Optional[str] = None, db: Session = Depends(get_db)):
    perro = db.query(Perro).filter(Perro.id == perro_id).first()
    if not perro:
        return RedirectResponse("/perros/", status_code=303)
    vacunas = sorted(perro.vacunas, key=lambda v: v.fecha_administracion, reverse=True)
    hoy_date = date.today()
    return templates.TemplateResponse(request, "perros/detail.html", {
        "perro": perro,
        "vacunas": vacunas,
        "pesos": perro.pesos,
        "celos": perro.celos,
        "medicaciones": perro.medicaciones,
        "ubicacion_actual": _ubicacion_actual(perro),
        "ubicacion_labels": UBICACION_LABELS,
        "hoy": hoy_date.isoformat(),
        "hoy_date": hoy_date,
        "tipos_ubicacion": [t.value for t in TipoUbicacion],
        "tipos_vacuna": TIPOS_VACUNA,
        "edad": _calcular_edad(perro.fecha_nacimiento),
        "error": error,
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


@router.post("/{perro_id}/editar", dependencies=[Depends(require_not_veterano)])
def editar_perro(
    request: Request,
    perro_id: int,
    nombre: str = Form(...),
    raza_id: int = Form(...),
    sexo: str = Form(...),
    esterilizado: Optional[str] = Form(None),
    ppp: Optional[str] = Form(None),
    fecha_entrada: date = Form(...),
    estado: str = Form("libre"),
    fecha_nacimiento: Optional[date] = Form(None),
    fecha_adopcion: Optional[date] = Form(None),
    num_chip: Optional[str] = Form(None),
    num_pasaporte: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    perro = db.query(Perro).filter(Perro.id == perro_id).first()
    if not perro:
        return RedirectResponse("/perros/", status_code=303)

    nuevo_estado = EstadoPerro(estado)
    estado_anterior = perro.estado
    fecha_adopcion_efectiva = fecha_adopcion if estado == "adoptado" else perro.fecha_adopcion

    if nuevo_estado == EstadoPerro.reservado and estado_anterior != EstadoPerro.reservado:
        perro.fecha_reserva = date.today()
    elif nuevo_estado != EstadoPerro.reservado:
        perro.fecha_reserva = None

    perro.nombre = nombre.upper()
    perro.raza_id = raza_id
    perro.sexo = Sexo(sexo)
    perro.esterilizado = esterilizado == "on"
    perro.ppp = ppp == "on"
    perro.fecha_entrada = fecha_entrada
    perro.estado = nuevo_estado
    perro.fecha_nacimiento = fecha_nacimiento
    perro.fecha_adopcion = fecha_adopcion_efectiva
    perro.num_chip = num_chip or None
    perro.num_pasaporte = num_pasaporte or None
    perro.color = color or None
    perro.notas = notas or None

    ubicacion_actual = _ubicacion_actual(perro)
    hoy = date.today()

    if nuevo_estado == EstadoPerro.adoptado and (
        ubicacion_actual is None or ubicacion_actual.tipo != TipoUbicacion.casa_adoptiva
    ):
        fecha_cambio = fecha_adopcion_efectiva or hoy
        if ubicacion_actual:
            ubicacion_actual.fecha_fin = fecha_cambio
        db.add(Ubicacion(perro_id=perro_id, tipo=TipoUbicacion.casa_adoptiva, fecha_inicio=fecha_cambio))

    elif nuevo_estado != EstadoPerro.adoptado and estado_anterior == EstadoPerro.adoptado and (
        ubicacion_actual and ubicacion_actual.tipo == TipoUbicacion.casa_adoptiva
    ):
        ubicacion_actual.fecha_fin = hoy
        db.add(Ubicacion(perro_id=perro_id, tipo=TipoUbicacion.refugio, fecha_inicio=hoy))

    db.commit()
    flash(request, "Cambios guardados.")
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/foto", dependencies=[Depends(require_not_veterano)])
def subir_foto(perro_id: int, foto: UploadFile = File(...), db: Session = Depends(get_db)):
    perro = db.query(Perro).filter(Perro.id == perro_id).first()
    if not perro:
        return RedirectResponse("/perros/", status_code=303)
    nueva_url = _subir_foto(foto, perro_id)
    if nueva_url:
        perro.foto_url = nueva_url
        db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/eliminar", dependencies=[Depends(require_not_veterano)])
def eliminar_perro(request: Request, perro_id: int, db: Session = Depends(get_db)):
    perro = db.query(Perro).filter(Perro.id == perro_id).first()
    if perro:
        nombre = perro.nombre
        db.delete(perro)
        db.commit()
        flash(request, f"Perro {nombre} eliminado.", "warning")
    return RedirectResponse("/perros/", status_code=303)


@router.post("/{perro_id}/vacuna", dependencies=[Depends(require_not_veterano)])
def agregar_vacuna(
    perro_id: int,
    tipo: str = Form(...),
    fecha_administracion: date = Form(...),
    fecha_proxima: Optional[date] = Form(None),
    veterinario: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not fecha_proxima:
        fecha_proxima = fecha_administracion.replace(year=fecha_administracion.year + 1)
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


@router.post("/{perro_id}/vacuna/{vacuna_id}/editar", dependencies=[Depends(require_not_veterano)])
def editar_vacuna(
    request: Request,
    perro_id: int,
    vacuna_id: int,
    tipo: str = Form(...),
    fecha_administracion: date = Form(...),
    fecha_proxima: Optional[date] = Form(None),
    veterinario: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    vacuna = db.query(Vacuna).filter(Vacuna.id == vacuna_id, Vacuna.perro_id == perro_id).first()
    if not vacuna:
        return RedirectResponse(f"/perros/{perro_id}", status_code=303)
    if not fecha_proxima:
        fecha_proxima = fecha_administracion.replace(year=fecha_administracion.year + 1)
    vacuna.tipo = tipo
    vacuna.fecha_administracion = fecha_administracion
    vacuna.fecha_proxima = fecha_proxima
    vacuna.veterinario = veterinario or None
    vacuna.notas = notas or None
    db.commit()
    flash(request, "Vacuna actualizada.")
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/vacuna/{vacuna_id}/eliminar", dependencies=[Depends(require_not_veterano)])
def eliminar_vacuna(
    request: Request,
    perro_id: int,
    vacuna_id: int,
    db: Session = Depends(get_db),
):
    vacuna = db.query(Vacuna).filter(Vacuna.id == vacuna_id, Vacuna.perro_id == perro_id).first()
    if vacuna:
        db.delete(vacuna)
        db.commit()
        flash(request, "Vacuna eliminada.", "warning")
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/ubicacion", dependencies=[Depends(require_not_veterano)])
def cambiar_ubicacion(
    request: Request,
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
    if ubicacion_actual and fecha_inicio < ubicacion_actual.fecha_inicio:
        return RedirectResponse(
            f"/perros/{perro_id}?error=La+fecha+de+inicio+no+puede+ser+anterior+a+la+ubicaci%C3%B3n+actual+%28{ubicacion_actual.fecha_inicio}%29",
            status_code=303
        )
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
    perro = db.query(Perro).filter(Perro.id == perro_id).first()
    if perro:
        if tipo == "casa_adoptiva":
            perro.estado = EstadoPerro.adoptado
            if not perro.fecha_adopcion:
                perro.fecha_adopcion = fecha_inicio
        elif tipo in ("refugio", "acogida", "residencia"):
            if perro.estado == EstadoPerro.adoptado:
                perro.estado = EstadoPerro.libre
    db.commit()
    flash(request, "Ubicación actualizada.")
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/ubicacion/{ubicacion_id}/editar", dependencies=[Depends(require_not_veterano)])
def editar_ubicacion(
    perro_id: int,
    ubicacion_id: int,
    tipo: str = Form(...),
    fecha_inicio: date = Form(...),
    fecha_fin: Optional[date] = Form(None),
    nombre_contacto: Optional[str] = Form(None),
    telefono_contacto: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    ubicacion = db.query(Ubicacion).filter(
        Ubicacion.id == ubicacion_id,
        Ubicacion.perro_id == perro_id,
    ).first()
    if not ubicacion:
        return RedirectResponse(f"/perros/{perro_id}", status_code=303)

    ubicacion.tipo = TipoUbicacion(tipo)
    ubicacion.fecha_inicio = fecha_inicio
    ubicacion.fecha_fin = fecha_fin or None
    ubicacion.nombre_contacto = nombre_contacto or None
    ubicacion.telefono_contacto = telefono_contacto or None
    ubicacion.notas = notas or None

    # Sincronizar estado del perro si es la ubicación activa (sin fecha_fin)
    if not ubicacion.fecha_fin:
        perro = db.query(Perro).filter(Perro.id == perro_id).first()
        if perro:
            if ubicacion.tipo == TipoUbicacion.casa_adoptiva:
                perro.estado = EstadoPerro.adoptado
                if not perro.fecha_adopcion:
                    perro.fecha_adopcion = fecha_inicio
            elif perro.estado == EstadoPerro.adoptado:
                perro.estado = EstadoPerro.libre

    db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/ubicacion/{ubicacion_id}/eliminar", dependencies=[Depends(require_not_veterano)])
def eliminar_ubicacion(perro_id: int, ubicacion_id: int, db: Session = Depends(get_db)):
    ubicacion = db.query(Ubicacion).filter(
        Ubicacion.id == ubicacion_id,
        Ubicacion.perro_id == perro_id,
    ).first()
    if not ubicacion:
        return RedirectResponse(f"/perros/{perro_id}", status_code=303)

    es_activa = ubicacion.fecha_fin is None
    db.delete(ubicacion)

    if es_activa:
        anterior = db.query(Ubicacion).filter(
            Ubicacion.perro_id == perro_id,
        ).order_by(Ubicacion.fecha_inicio.desc()).first()
        if anterior:
            anterior.fecha_fin = None
            perro = db.query(Perro).filter(Perro.id == perro_id).first()
            if perro:
                if anterior.tipo == TipoUbicacion.casa_adoptiva:
                    perro.estado = EstadoPerro.adoptado
                else:
                    perro.estado = EstadoPerro.libre

    db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/peso", dependencies=[Depends(require_not_veterano)])
def agregar_peso(
    perro_id: int,
    fecha: date = Form(...),
    peso_kg: float = Form(...),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    db.add(PesoPerro(perro_id=perro_id, fecha=fecha, peso_kg=peso_kg, notas=notas or None))
    db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/peso/{peso_id}/eliminar", dependencies=[Depends(require_not_veterano)])
def eliminar_peso(perro_id: int, peso_id: int, db: Session = Depends(get_db)):
    peso = db.query(PesoPerro).filter(PesoPerro.id == peso_id, PesoPerro.perro_id == perro_id).first()
    if peso:
        db.delete(peso)
        db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/celo", dependencies=[Depends(require_not_veterano)])
def agregar_celo(
    perro_id: int,
    fecha_inicio: date = Form(...),
    fecha_fin: Optional[date] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    db.add(CeloPerro(perro_id=perro_id, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, notas=notas or None))
    db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/celo/{celo_id}/eliminar", dependencies=[Depends(require_not_veterano)])
def eliminar_celo(perro_id: int, celo_id: int, db: Session = Depends(get_db)):
    celo = db.query(CeloPerro).filter(CeloPerro.id == celo_id, CeloPerro.perro_id == perro_id).first()
    if celo:
        db.delete(celo)
        db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/medicacion", dependencies=[Depends(require_not_veterano)])
def agregar_medicacion(
    perro_id: int,
    medicamento: str = Form(...),
    dosis: Optional[str] = Form(None),
    frecuencia: Optional[str] = Form(None),
    turno: List[str] = Form(default=[]),
    fecha_inicio: date = Form(...),
    fecha_fin: Optional[date] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    db.add(MedicacionPerro(
        perro_id=perro_id,
        medicamento=medicamento.strip(),
        dosis=dosis or None,
        frecuencia=frecuencia or None,
        turno=",".join(turno) if turno else None,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin or None,
        notas=notas or None,
    ))
    db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/medicacion/{med_id}/editar", dependencies=[Depends(require_not_veterano)])
def editar_medicacion(
    perro_id: int,
    med_id: int,
    medicamento: str = Form(...),
    dosis: Optional[str] = Form(None),
    frecuencia: Optional[str] = Form(None),
    turno: List[str] = Form(default=[]),
    fecha_inicio: date = Form(...),
    fecha_fin: Optional[date] = Form(None),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    med = db.query(MedicacionPerro).filter(MedicacionPerro.id == med_id, MedicacionPerro.perro_id == perro_id).first()
    if med:
        med.medicamento = medicamento.strip()
        med.dosis = dosis or None
        med.frecuencia = frecuencia or None
        med.turno = ",".join(turno) if turno else None
        med.fecha_inicio = fecha_inicio
        med.fecha_fin = fecha_fin or None
        med.notas = notas or None
        db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)


@router.post("/{perro_id}/medicacion/{med_id}/eliminar", dependencies=[Depends(require_not_veterano)])
def eliminar_medicacion(perro_id: int, med_id: int, db: Session = Depends(get_db)):
    med = db.query(MedicacionPerro).filter(MedicacionPerro.id == med_id, MedicacionPerro.perro_id == perro_id).first()
    if med:
        db.delete(med)
        db.commit()
    return RedirectResponse(f"/perros/{perro_id}", status_code=303)
