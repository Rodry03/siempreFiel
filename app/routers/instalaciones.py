from datetime import date
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.auth import get_current_user, require_not_veterano, NotAuthorized, flash
from app.database import get_db
from app.models import IncidenciaInstalacion, PrioridadIncidencia, EstadoIncidencia, Voluntario
from app.templates_config import templates

router = APIRouter(
    prefix="/instalaciones",
    dependencies=[Depends(get_current_user)],
)

PRIORIDAD_LABELS = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
    "urgente": "Urgente",
}

PRIORIDAD_COLORS = {
    "baja": "secondary",
    "media": "primary",
    "alta": "warning",
    "urgente": "danger",
}

ESTADO_LABELS = {
    "pendiente": "Pendiente",
    "en_proceso": "En proceso",
    "resuelto": "Resuelto",
}

ESTADO_COLORS = {
    "pendiente": "danger",
    "en_proceso": "warning",
    "resuelto": "success",
}

_PRIORIDAD_ORDER = {"urgente": 0, "alta": 1, "media": 2, "baja": 3}


def _ctx():
    return {
        "prioridades": [p.value for p in PrioridadIncidencia],
        "prioridad_labels": PRIORIDAD_LABELS,
        "prioridad_colors": PRIORIDAD_COLORS,
        "estados": [e.value for e in EstadoIncidencia],
        "estado_labels": ESTADO_LABELS,
        "estado_colors": ESTADO_COLORS,
    }


def _check_puede_editar(request: Request, inc: IncidenciaInstalacion):
    user = request.state.current_user
    if user.rol.value == "veterano" and inc.creado_por_id != user.id:
        raise NotAuthorized()


def _voluntarios_activos(db: Session):
    return (
        db.query(Voluntario)
        .filter(Voluntario.activo == True)
        .order_by(Voluntario.nombre, Voluntario.apellido)
        .all()
    )


@router.get("/")
def listar_incidencias(
    request: Request,
    estado: str = "activo",
    prioridad: str = "todas",
    db: Session = Depends(get_db),
):
    q = db.query(IncidenciaInstalacion)
    if estado == "activo":
        q = q.filter(IncidenciaInstalacion.estado != EstadoIncidencia.resuelto)
    elif estado in [e.value for e in EstadoIncidencia]:
        q = q.filter(IncidenciaInstalacion.estado == estado)
    if prioridad in [p.value for p in PrioridadIncidencia]:
        q = q.filter(IncidenciaInstalacion.prioridad == prioridad)
    incidencias = q.order_by(IncidenciaInstalacion.fecha_reporte.desc()).all()
    incidencias.sort(key=lambda i: (_PRIORIDAD_ORDER.get(i.prioridad.value, 99), -i.id))
    return templates.TemplateResponse(request, "instalaciones/list.html", {
        **_ctx(),
        "incidencias": incidencias,
        "estado_filtro": estado,
        "prioridad_filtro": prioridad,
    })


@router.get("/nueva")
def form_nueva(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "instalaciones/form.html", {
        **_ctx(),
        "incidencia": None,
        "hoy": date.today(),
        "voluntarios": _voluntarios_activos(db),
        "usuario_actual": request.state.current_user,
    })


@router.post("/nueva")
def crear_incidencia(
    request: Request,
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    zona: Optional[str] = Form(None),
    prioridad: str = Form(...),
    estado: str = Form("pendiente"),
    fecha_reporte: date = Form(...),
    reportado_por: Optional[str] = Form(None),
    fecha_resolucion: Optional[date] = Form(None),
    resuelto_por: Optional[str] = Form(None),
    notas_resolucion: Optional[str] = Form(None),
    coste: Optional[float] = Form(None),
    db: Session = Depends(get_db),
):
    es_resuelto = estado == EstadoIncidencia.resuelto.value
    inc = IncidenciaInstalacion(
        titulo=titulo,
        descripcion=descripcion or None,
        zona=zona or None,
        prioridad=prioridad,
        estado=estado,
        fecha_reporte=fecha_reporte,
        reportado_por=reportado_por or None,
        fecha_resolucion=fecha_resolucion if es_resuelto else None,
        resuelto_por=(resuelto_por or None) if es_resuelto else None,
        notas_resolucion=(notas_resolucion or None) if es_resuelto else None,
        coste=coste if es_resuelto else None,
        creado_por_id=request.state.current_user.id,
    )
    db.add(inc)
    db.commit()
    flash(request, "Incidencia registrada.", "success")
    return RedirectResponse("/instalaciones/", status_code=303)


@router.get("/{inc_id}")
def detalle_incidencia(request: Request, inc_id: int, db: Session = Depends(get_db)):
    inc = db.query(IncidenciaInstalacion).filter(IncidenciaInstalacion.id == inc_id).first()
    if not inc:
        raise HTTPException(status_code=404)
    user = request.state.current_user
    puede_editar = user.rol.value != "veterano" or inc.creado_por_id == user.id
    return templates.TemplateResponse(request, "instalaciones/detail.html", {
        **_ctx(),
        "incidencia": inc,
        "puede_editar": puede_editar,
    })


@router.get("/{inc_id}/editar")
def form_editar(request: Request, inc_id: int, db: Session = Depends(get_db)):
    inc = db.query(IncidenciaInstalacion).filter(IncidenciaInstalacion.id == inc_id).first()
    if not inc:
        raise HTTPException(status_code=404)
    _check_puede_editar(request, inc)
    return templates.TemplateResponse(request, "instalaciones/form.html", {
        **_ctx(),
        "incidencia": inc,
        "hoy": date.today(),
        "voluntarios": _voluntarios_activos(db),
        "usuario_actual": request.state.current_user,
    })


@router.post("/{inc_id}/editar")
def editar_incidencia(
    request: Request,
    inc_id: int,
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    zona: Optional[str] = Form(None),
    prioridad: str = Form(...),
    estado: str = Form(...),
    fecha_reporte: date = Form(...),
    reportado_por: Optional[str] = Form(None),
    fecha_resolucion: Optional[date] = Form(None),
    resuelto_por: Optional[str] = Form(None),
    notas_resolucion: Optional[str] = Form(None),
    coste: Optional[float] = Form(None),
    db: Session = Depends(get_db),
):
    inc = db.query(IncidenciaInstalacion).filter(IncidenciaInstalacion.id == inc_id).first()
    if not inc:
        raise HTTPException(status_code=404)
    _check_puede_editar(request, inc)
    es_resuelto = estado == EstadoIncidencia.resuelto.value
    inc.titulo = titulo
    inc.descripcion = descripcion or None
    inc.zona = zona or None
    inc.prioridad = prioridad
    inc.estado = estado
    inc.fecha_reporte = fecha_reporte
    inc.reportado_por = reportado_por or None
    inc.fecha_resolucion = fecha_resolucion if es_resuelto else None
    inc.resuelto_por = (resuelto_por or None) if es_resuelto else None
    inc.notas_resolucion = (notas_resolucion or None) if es_resuelto else None
    inc.coste = coste if es_resuelto else None
    db.commit()
    flash(request, "Incidencia actualizada.", "success")
    return RedirectResponse(f"/instalaciones/{inc_id}", status_code=303)


@router.post("/{inc_id}/eliminar")
def eliminar_incidencia(request: Request, inc_id: int, db: Session = Depends(get_db)):
    inc = db.query(IncidenciaInstalacion).filter(IncidenciaInstalacion.id == inc_id).first()
    if inc:
        _check_puede_editar(request, inc)
        db.delete(inc)
        db.commit()
    flash(request, "Incidencia eliminada.", "success")
    return RedirectResponse("/instalaciones/", status_code=303)
