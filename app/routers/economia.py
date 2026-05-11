from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.auth import get_current_user, require_not_veterano, flash
from app.database import get_db
from app.models import MovimientoEconomico, TipoMovimiento
from app.templates_config import templates

router = APIRouter(
    prefix="/economia",
    dependencies=[Depends(get_current_user), Depends(require_not_veterano)],
)

TIPO_LABELS = {"ingreso": "Ingreso", "gasto": "Gasto", "deuda": "Deuda"}
TIPO_COLORS = {"ingreso": "success", "gasto": "danger", "deuda": "warning"}


@router.get("/")
def listar(request: Request, tipo: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(MovimientoEconomico)
    if tipo in ("ingreso", "gasto", "deuda"):
        q = q.filter(MovimientoEconomico.tipo == TipoMovimiento(tipo))
    movimientos = q.order_by(MovimientoEconomico.fecha.desc()).all()

    todos = db.query(MovimientoEconomico).all()
    total_ingresos = sum(m.importe for m in todos if m.tipo == TipoMovimiento.ingreso)
    total_gastos = sum(m.importe for m in todos if m.tipo == TipoMovimiento.gasto)
    deuda_pendiente = sum(m.importe for m in todos if m.tipo == TipoMovimiento.deuda and not m.pagado)

    return templates.TemplateResponse(request, "economia/list.html", {
        "movimientos": movimientos,
        "tipo_filtro": tipo or "",
        "tipo_labels": TIPO_LABELS,
        "tipo_colors": TIPO_COLORS,
        "total_ingresos": total_ingresos,
        "total_gastos": total_gastos,
        "balance": total_ingresos - total_gastos,
        "deuda_pendiente": deuda_pendiente,
        "hoy": date.today().isoformat(),
    })


@router.post("/nuevo")
def crear(
    request: Request,
    tipo: str = Form(...),
    concepto: str = Form(...),
    categoria: Optional[str] = Form(None),
    importe: float = Form(...),
    fecha: date = Form(...),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    db.add(MovimientoEconomico(
        tipo=TipoMovimiento(tipo),
        concepto=concepto.strip(),
        categoria=categoria.strip() if categoria else None,
        importe=round(importe, 2),
        fecha=fecha,
        notas=notas or None,
    ))
    db.commit()
    flash(request, "Movimiento registrado.")
    return RedirectResponse(f"/economia/?tipo={tipo}", status_code=303)


@router.post("/{mov_id}/editar")
def editar(
    request: Request,
    mov_id: int,
    tipo: str = Form(...),
    concepto: str = Form(...),
    categoria: Optional[str] = Form(None),
    importe: float = Form(...),
    fecha: date = Form(...),
    notas: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    mov = db.query(MovimientoEconomico).filter(MovimientoEconomico.id == mov_id).first()
    if mov:
        mov.tipo = TipoMovimiento(tipo)
        mov.concepto = concepto.strip()
        mov.categoria = categoria.strip() if categoria else None
        mov.importe = round(importe, 2)
        mov.fecha = fecha
        mov.notas = notas or None
        db.commit()
        flash(request, "Movimiento actualizado.")
    return RedirectResponse("/economia/", status_code=303)


@router.post("/{mov_id}/eliminar")
def eliminar(request: Request, mov_id: int, db: Session = Depends(get_db)):
    mov = db.query(MovimientoEconomico).filter(MovimientoEconomico.id == mov_id).first()
    if mov:
        db.delete(mov)
        db.commit()
        flash(request, "Movimiento eliminado.", "warning")
    return RedirectResponse("/economia/", status_code=303)


@router.post("/{mov_id}/marcar-pagado")
def marcar_pagado(mov_id: int, db: Session = Depends(get_db)):
    mov = db.query(MovimientoEconomico).filter(MovimientoEconomico.id == mov_id).first()
    if mov and mov.tipo == TipoMovimiento.deuda:
        mov.pagado = not mov.pagado
        db.commit()
    return RedirectResponse("/economia/?tipo=deuda", status_code=303)
