from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from typing import Optional
from app.auth import get_current_user, require_admin, flash
from app.database import get_db
from app.estadillo_parser import parse_estadillo, buscar_voluntario
from app.models import TurnoVoluntario, EstadoTurno, Voluntario, PerfilVoluntario
from app.routers.turnos import (
    PERFIL_LABELS, PERFIL_COLORS, PERFILES_SIN_TURNOS,
    DIAS_ES, FRANJA_LABELS, calcular_saldo,
)
from app.templates_config import templates

router = APIRouter(
    prefix="/turnos",
    dependencies=[Depends(get_current_user), Depends(require_admin)],
)


def _semana_lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _era_veterano_en_fecha(v: Voluntario, fecha: date) -> bool:
    if v.perfil == PerfilVoluntario.apoyo_en_junta:
        return True
    return (
        v.fecha_veterano is not None
        and v.fecha_veterano <= fecha
        and (v.fecha_fin_veterano is None or v.fecha_fin_veterano >= fecha)
    )


@router.get("/")
def listar_turnos(
    request: Request,
    semana: Optional[str] = None,
    perfil: Optional[str] = None,
    db: Session = Depends(get_db),
):
    hoy = date.today()
    if semana:
        try:
            semana_date = _semana_lunes(date.fromisoformat(semana))
        except ValueError:
            semana_date = _semana_lunes(hoy)
    else:
        semana_date = _semana_lunes(hoy)

    semana_fin = semana_date + timedelta(days=6)

    q = (
        db.query(Voluntario)
        .filter(Voluntario.activo == True, Voluntario.perfil.notin_(list(PERFILES_SIN_TURNOS)))
    )
    if perfil:
        try:
            q = q.filter(Voluntario.perfil == PerfilVoluntario(perfil))
        except ValueError:
            perfil = None
    voluntarios = q.order_by(Voluntario.nombre, Voluntario.apellido).all()

    turnos_semana = (
        db.query(TurnoVoluntario)
        .filter(TurnoVoluntario.fecha >= semana_date, TurnoVoluntario.fecha <= semana_fin)
        .all()
    )

    turnos_por_vol = {}
    for t in turnos_semana:
        turnos_por_vol.setdefault(t.voluntario_id, []).append(t)
    for v_id in turnos_por_vol:
        turnos_por_vol[v_id].sort(key=lambda t: (t.fecha, t.franja.value))

    def _valor(t):
        return 0.5 if t.estado == EstadoTurno.medio_turno else 1.0

    def _en_apoyo(v):
        return any(
            p.fecha_inicio <= semana_fin and (p.fecha_fin is None or p.fecha_fin >= semana_date)
            for p in v.periodos_apoyo
        )

    voluntarios_data = [
        {
            "voluntario": v,
            "saldo": calcular_saldo(v),
            "turnos": turnos_por_vol.get(v.id, []),
            "total_valor": sum(_valor(t) for t in turnos_por_vol.get(v.id, [])),
            "en_apoyo": _en_apoyo(v),
        }
        for v in voluntarios
    ]

    dias = [semana_date + timedelta(days=i) for i in range(7)]
    perfiles_con_turnos = [p.value for p in PerfilVoluntario if p not in PERFILES_SIN_TURNOS]

    return templates.TemplateResponse(request, "turnos/list.html", {
        "semana": semana_date,
        "semana_fin": semana_fin,
        "semana_label": f"{semana_date.strftime('%d/%m')} – {semana_fin.strftime('%d/%m/%Y')}",
        "semana_anterior": (semana_date - timedelta(days=7)).isoformat(),
        "semana_siguiente": (semana_date + timedelta(days=7)).isoformat(),
        "dias": dias,
        "voluntarios_data": voluntarios_data,
        "perfil_labels": PERFIL_LABELS,
        "perfil_colors": PERFIL_COLORS,
        "dias_labels": DIAS_ES,
        "franja_labels": FRANJA_LABELS,
        "perfil_filtro": perfil or "",
        "perfiles_con_turnos": perfiles_con_turnos,
    })


@router.post("/anadir")
async def anadir_turno(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    semana_str = form.get("semana", "")
    perfil_str = form.get("perfil_filtro", "")
    perfil_qs = f"&perfil={perfil_str}" if perfil_str else ""
    try:
        voluntario_id = int(form.get("voluntario_id"))
        fecha = date.fromisoformat(form.get("fecha"))
        franja = form.get("franja")
        tipo = form.get("tipo", "completo")
    except (ValueError, TypeError):
        flash(request, "Datos inválidos.", "danger")
        return RedirectResponse(f"/turnos/?semana={semana_str}{perfil_qs}", status_code=303)

    existing = db.query(TurnoVoluntario).filter(
        TurnoVoluntario.voluntario_id == voluntario_id,
        TurnoVoluntario.fecha == fecha,
        TurnoVoluntario.franja == franja,
    ).first()

    if existing:
        return RedirectResponse(f"/turnos/?semana={semana_str}", status_code=303)

    estado = EstadoTurno.medio_turno if tipo == "medio" else EstadoTurno.realizado

    # Regla automática: si hay 2+ veteranos en el mismo hueco (según fecha) → medio_turno a todos
    if estado == EstadoTurno.realizado:
        voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
        if voluntario and _era_veterano_en_fecha(voluntario, fecha):
            otros_vet = (
                db.query(TurnoVoluntario)
                .join(Voluntario, TurnoVoluntario.voluntario_id == Voluntario.id)
                .filter(
                    TurnoVoluntario.fecha == fecha,
                    TurnoVoluntario.franja == franja,
                    TurnoVoluntario.voluntario_id != voluntario_id,
                    TurnoVoluntario.estado == EstadoTurno.realizado,
                    or_(
                        Voluntario.perfil == PerfilVoluntario.apoyo_en_junta,
                        and_(
                            Voluntario.fecha_veterano != None,
                            Voluntario.fecha_veterano <= fecha,
                            or_(
                                Voluntario.fecha_fin_veterano == None,
                                Voluntario.fecha_fin_veterano >= fecha,
                            ),
                        ),
                    ),
                )
                .all()
            )
            if otros_vet:
                for t in otros_vet:
                    t.estado = EstadoTurno.medio_turno
                estado = EstadoTurno.medio_turno

    db.add(TurnoVoluntario(
        voluntario_id=voluntario_id,
        fecha=fecha,
        franja=franja,
        estado=estado,
    ))
    db.commit()
    return RedirectResponse(f"/turnos/?semana={semana_str}{perfil_qs}", status_code=303)


@router.post("/{turno_id}/eliminar")
async def eliminar_turno(request: Request, turno_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    semana_str = form.get("semana", "")
    perfil_str = form.get("perfil_filtro", "")
    perfil_qs = f"&perfil={perfil_str}" if perfil_str else ""
    turno = db.query(TurnoVoluntario).filter(TurnoVoluntario.id == turno_id).first()
    if turno:
        db.delete(turno)
        db.commit()
    return RedirectResponse(f"/turnos/?semana={semana_str}{perfil_qs}", status_code=303)


@router.post("/limpiar-semana", dependencies=[Depends(require_admin)])
async def limpiar_semana(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    semana_str = form.get("semana", "")
    try:
        semana_date = _semana_lunes(date.fromisoformat(semana_str))
    except ValueError:
        semana_date = _semana_lunes(date.today())
    semana_fin = semana_date + timedelta(days=6)
    eliminados = (
        db.query(TurnoVoluntario)
        .filter(TurnoVoluntario.fecha >= semana_date, TurnoVoluntario.fecha <= semana_fin)
        .all()
    )
    for t in eliminados:
        db.delete(t)
    db.commit()
    flash(request, f"{len(eliminados)} turno(s) eliminado(s) de la semana del {semana_date.strftime('%d/%m/%Y')}.", "warning")
    return RedirectResponse(f"/turnos/?semana={semana_date.isoformat()}", status_code=303)


@router.get("/estadillo")
def estadillo_form(request: Request):
    return templates.TemplateResponse(request, "turnos/estadillo_form.html", {})


@router.post("/estadillo/previsualizar")
async def estadillo_previsualizar(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    texto = form.get("texto", "").strip()

    if not texto:
        flash(request, "Pega el estadillo antes de continuar.", "danger")
        return templates.TemplateResponse(request, "turnos/estadillo_form.html", {"texto": ""})

    fecha_inicio, slots = parse_estadillo(texto)

    if not fecha_inicio:
        flash(request, "No se detectó la fecha. Asegúrate de que el texto incluye el encabezado (ej: ESTADILLO 28 JULIO - 3 AGOSTO).", "danger")
        return templates.TemplateResponse(request, "turnos/estadillo_form.html", {"texto": texto})

    todos = db.query(Voluntario).all()
    slots_preview = []
    no_encontrados = []
    total_insertar = 0

    for fecha, franja, personas in slots:
        if not personas:
            slots_preview.append({"fecha": fecha, "franja": franja, "personas": [], "skip": True})
            continue

        slot_personas = []
        for nombre_raw, es_vet, es_medio in personas:
            v = buscar_voluntario(todos, nombre_raw)
            if v:
                total_insertar += 1
                slot_personas.append({"nombre_raw": nombre_raw, "voluntario": v, "es_vet": es_vet, "es_medio": es_medio, "ok": True})
            else:
                no_encontrados.append({"nombre_raw": nombre_raw, "fecha": fecha, "franja": franja})
                slot_personas.append({"nombre_raw": nombre_raw, "voluntario": None, "es_vet": es_vet, "es_medio": es_medio, "ok": False})

        slots_preview.append({"fecha": fecha, "franja": franja, "personas": slot_personas, "skip": False})

    return templates.TemplateResponse(request, "turnos/estadillo_preview.html", {
        "fecha_inicio": fecha_inicio,
        "slots_preview": slots_preview,
        "no_encontrados": no_encontrados,
        "total_insertar": total_insertar,
        "texto": texto,
        "dias_labels": DIAS_ES,
        "franja_labels": FRANJA_LABELS,
    })


@router.post("/estadillo/insertar")
async def estadillo_insertar(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    texto = form.get("texto", "")

    fecha_inicio, slots = parse_estadillo(texto)
    todos = db.query(Voluntario).all()

    PERFILES_VET = {PerfilVoluntario.veterano, PerfilVoluntario.apoyo_en_junta}
    insertados = 0
    omitidos = 0

    for fecha, franja, personas in slots:
        if not personas:
            continue

        for nombre_raw, _, es_medio in personas:
            v = buscar_voluntario(todos, nombre_raw)
            if not v:
                continue
            existe = db.query(TurnoVoluntario).filter(
                TurnoVoluntario.voluntario_id == v.id,
                TurnoVoluntario.fecha == fecha,
                TurnoVoluntario.franja == franja,
            ).first()
            if existe:
                omitidos += 1
                continue
            db.add(TurnoVoluntario(
                voluntario_id=v.id,
                fecha=fecha,
                franja=franja,
                estado=EstadoTurno.medio_turno if es_medio else EstadoTurno.realizado,
            ))
            insertados += 1

        # Apply medio_turno rule: 2+ vets in same slot → all become medio_turno
        # Only counts people who were actually veterans on that date
        db.flush()
        vets_slot = (
            db.query(TurnoVoluntario)
            .join(Voluntario, TurnoVoluntario.voluntario_id == Voluntario.id)
            .filter(
                TurnoVoluntario.fecha == fecha,
                TurnoVoluntario.franja == franja,
                TurnoVoluntario.estado == EstadoTurno.realizado,
                or_(
                    Voluntario.perfil == PerfilVoluntario.apoyo_en_junta,
                    and_(
                        Voluntario.fecha_veterano != None,
                        Voluntario.fecha_veterano <= fecha,
                        or_(
                            Voluntario.fecha_fin_veterano == None,
                            Voluntario.fecha_fin_veterano >= fecha,
                        ),
                    ),
                ),
            )
            .all()
        )
        if len(vets_slot) >= 2:
            for t in vets_slot:
                t.estado = EstadoTurno.medio_turno

    db.commit()

    msg = f"{insertados} turno(s) insertado(s)."
    if omitidos:
        msg += f" {omitidos} omitido(s) por ya existir."
    flash(request, msg)
    semana_str = fecha_inicio.isoformat() if fecha_inicio else date.today().isoformat()
    return RedirectResponse(f"/turnos/?semana={semana_str}", status_code=303)
