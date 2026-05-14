from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import Optional
from app.auth import get_current_user, require_not_veterano, flash
from app.database import get_db
from app.models import Voluntario, PerfilVoluntario, EstadoTurno
from app.routers.voluntarios import CONTRATO_LABELS, CONTRATO_COLORS
from app.templates_config import templates

router = APIRouter(prefix="/voluntarios", dependencies=[Depends(get_current_user)])

PERFIL_LABELS = {
    "directiva": "Directiva",
    "apoyo_en_junta": "Apoyo en Junta",
    "veterano": "Veterano",
    "voluntario": "Voluntario",
    "guagua": "Guagua",
    "eventos": "Eventos",
    "colaboradores": "Colaboradores",
}
PERFIL_COLORS = {
    "directiva": "danger",
    "apoyo_en_junta": "dark",
    "veterano": "warning",
    "voluntario": "success",
    "guagua": "primary",
    "eventos": "info",
    "colaboradores": "secondary",
}

PERFILES_SIN_TURNOS = {
    PerfilVoluntario.directiva,
    PerfilVoluntario.guagua,
    PerfilVoluntario.eventos,
    PerfilVoluntario.colaboradores,
}

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

DIAS_ES = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
FRANJA_LABELS = {"manana": "Mañana", "tarde": "Tarde"}

FECHA_INICIO_SALDO = date(2025, 8, 4)


def _mes_semana(lunes: date) -> tuple:
    """Devuelve (year, month) del mes al que pertenece la semana por mayoría de días."""
    domingo = lunes + timedelta(days=6)
    if lunes.month == domingo.month:
        return (lunes.year, lunes.month)
    dias_en_mes_lunes = sum(1 for i in range(7) if (lunes + timedelta(days=i)).month == lunes.month)
    if dias_en_mes_lunes >= 4:
        return (lunes.year, lunes.month)
    return (domingo.year, domingo.month)


def calcular_tiempo_voluntario(fecha_alta) -> str:
    hoy = date.today()
    anos = hoy.year - fecha_alta.year - ((hoy.month, hoy.day) < (fecha_alta.month, fecha_alta.day))
    if anos == 0:
        meses = (hoy.year - fecha_alta.year) * 12 + hoy.month - fecha_alta.month
        if hoy.day < fecha_alta.day:
            meses -= 1
        return f"{meses} mes{'es' if meses != 1 else ''}"
    return f"{anos} año{'s' if anos != 1 else ''}"


def calcular_saldo(voluntario: Voluntario) -> float:
    effective_start = max(FECHA_INICIO_SALDO, voluntario.fecha_veterano or voluntario.fecha_alta)
    first_monday = effective_start - timedelta(days=effective_start.weekday())
    today = date.today()

    saldo = 0.0
    week_start = first_monday
    while week_start + timedelta(days=6) <= today:
        week_end = week_start + timedelta(days=6)
        week_turns = [t for t in voluntario.turnos if week_start <= t.fecha <= week_end]
        en_apoyo = any(
            p.fecha_inicio <= week_end and (p.fecha_fin is None or p.fecha_fin >= week_start)
            for p in voluntario.periodos_apoyo
        )
        if not en_apoyo:
            week_value = sum(
                0.5 if t.estado == EstadoTurno.medio_turno else 1.0
                for t in week_turns
                if t.estado in (EstadoTurno.realizado, EstadoTurno.medio_turno)
            )
            saldo += week_value - 1.0
        week_start += timedelta(days=7)

    return saldo


@router.get("/{voluntario_id}")
def detalle_voluntario(request: Request, voluntario_id: int, db: Session = Depends(get_db)):
    from app.models import RolUsuario
    current_user = request.state.current_user
    if current_user.rol == RolUsuario.veterano:
        if not current_user.voluntario_id or current_user.voluntario_id != voluntario_id:
            from app.auth import NotAuthorized
            raise NotAuthorized()
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if not voluntario:
        return RedirectResponse("/voluntarios/", status_code=303)
    hace_turnos = voluntario.perfil not in PERFILES_SIN_TURNOS
    saldo = calcular_saldo(voluntario) if hace_turnos else None
    total_turnos = len(voluntario.turnos) if hace_turnos else 0
    tiempo_voluntario = calcular_tiempo_voluntario(voluntario.fecha_alta)

    FECHA_HISTORIAL = date(2025, 8, 4)
    turnos_recientes = []
    if hace_turnos:
        hoy_turnos = date.today()
        primer_lunes_raw = max(FECHA_HISTORIAL, voluntario.fecha_alta)
        primer_lunes = primer_lunes_raw - timedelta(days=primer_lunes_raw.weekday())
        semana_hoy_lunes = hoy_turnos - timedelta(days=hoy_turnos.weekday())

        por_semana = defaultdict(list)
        for t in voluntario.turnos:
            lunes = t.fecha - timedelta(days=t.fecha.weekday())
            if lunes >= primer_lunes:
                por_semana[lunes].append(t)
        for semana_turnos in por_semana.values():
            semana_turnos.sort(key=lambda t: (t.fecha, t.franja.value))

        lunes = primer_lunes
        while lunes <= semana_hoy_lunes:
            lunes_fin = lunes + timedelta(days=6)
            turnos = por_semana.get(lunes, [])
            en_apoyo = any(
                p.fecha_inicio <= lunes_fin and (p.fecha_fin is None or p.fecha_fin >= lunes)
                for p in voluntario.periodos_apoyo
            )
            es_actual = lunes == semana_hoy_lunes
            if en_apoyo or es_actual:
                saldo_semana = None
            else:
                wv = sum(
                    0.5 if t.estado == EstadoTurno.medio_turno else 1.0
                    for t in turnos
                    if t.estado in (EstadoTurno.realizado, EstadoTurno.medio_turno)
                )
                saldo_semana = wv - 1.0
            mes_key = _mes_semana(lunes)
            mes_label = f"{MESES_ES[mes_key[1]]} {mes_key[0]}"
            turnos_recientes.append({
                "semana": lunes,
                "semana_fin": lunes_fin,
                "turnos": turnos,
                "en_apoyo": en_apoyo,
                "sin_turno": not turnos and not en_apoyo and not es_actual,
                "es_actual": es_actual,
                "saldo_semana": saldo_semana,
                "mes": mes_key,
                "mes_label": mes_label,
            })
            lunes += timedelta(days=7)
        turnos_recientes.reverse()

        resumen_mensual = {}
        for entry in turnos_recientes:
            mk = entry["mes"]
            if mk not in resumen_mensual:
                resumen_mensual[mk] = {"label": entry["mes_label"], "realizados": 0, "medio": 0}
            for t in entry["turnos"]:
                if t.estado == EstadoTurno.realizado:
                    resumen_mensual[mk]["realizados"] += 1
                elif t.estado == EstadoTurno.medio_turno:
                    resumen_mensual[mk]["medio"] += 1

    from app.models import MiembroGrupoTarea, EjecucionGrupoTarea
    hoy = date.today()
    semana_actual = hoy - timedelta(days=hoy.weekday())
    memberships = db.query(MiembroGrupoTarea).filter(MiembroGrupoTarea.voluntario_id == voluntario_id).all()
    grupos_voluntario = []
    for m in memberships:
        ej = db.query(EjecucionGrupoTarea).filter(
            EjecucionGrupoTarea.grupo_id == m.grupo_id,
            EjecucionGrupoTarea.semana == semana_actual,
        ).first()
        grupos_voluntario.append({"grupo": m.grupo, "ejecucion": ej})

    hoy_date = date.today()
    tiene_apoyo_activo = hace_turnos and any(
        p.fecha_inicio <= hoy_date and (p.fecha_fin is None or p.fecha_fin >= hoy_date)
        for p in voluntario.periodos_apoyo
    )

    return templates.TemplateResponse(request, "voluntarios/detail.html", {
        "voluntario": voluntario,
        "hace_turnos": hace_turnos,
        "tiene_apoyo_activo": tiene_apoyo_activo,
        "saldo": saldo,
        "perfiles": [p.value for p in PerfilVoluntario],
        "perfil_labels": PERFIL_LABELS,
        "perfil_colors": PERFIL_COLORS,
        "contrato_labels": CONTRATO_LABELS,
        "contrato_colors": CONTRATO_COLORS,
        "total_turnos": total_turnos,
        "tiempo_voluntario": tiempo_voluntario,
        "grupos_voluntario": grupos_voluntario,
        "semana_actual": semana_actual,
        "turnos_recientes": turnos_recientes,
        "resumen_mensual": resumen_mensual if hace_turnos else {},
        "dias_labels": DIAS_ES,
        "franja_labels": FRANJA_LABELS,
    })


def _solo_propio(request, voluntario_id: int):
    from app.models import RolUsuario
    from app.auth import NotAuthorized
    u = request.state.current_user
    if u.rol != RolUsuario.veterano or u.voluntario_id != voluntario_id:
        raise NotAuthorized()


@router.get("/{voluntario_id}/editar-datos")
def form_editar_datos(request: Request, voluntario_id: int, db: Session = Depends(get_db)):
    _solo_propio(request, voluntario_id)
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if not voluntario:
        return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)
    return templates.TemplateResponse(request, "voluntarios/editar_datos.html", {
        "voluntario": voluntario,
    })


@router.post("/{voluntario_id}/editar-datos")
def editar_datos(
    request: Request,
    voluntario_id: int,
    nombre: str = Form(...),
    apellido: str = Form(...),
    telefono: Optional[str] = Form(None),
    fecha_alta: Optional[str] = Form(None),
    fecha_veterano: Optional[str] = Form(None),
    dni: Optional[str] = Form(None),
    email: str = Form(...),
    direccion: Optional[str] = Form(None),
    ciudad: Optional[str] = Form(None),
    provincia: Optional[str] = Form(None),
    codigo_postal: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    _solo_propio(request, voluntario_id)
    voluntario = db.query(Voluntario).filter(Voluntario.id == voluntario_id).first()
    if not voluntario:
        return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)
    voluntario.nombre = nombre.strip()
    voluntario.apellido = apellido.strip()
    voluntario.telefono = telefono or None
    if fecha_alta:
        from datetime import date
        try:
            voluntario.fecha_alta = date.fromisoformat(fecha_alta)
        except ValueError:
            pass
    if fecha_veterano:
        try:
            voluntario.fecha_veterano = date.fromisoformat(fecha_veterano)
        except ValueError:
            pass
    else:
        voluntario.fecha_veterano = None
    voluntario.dni = dni or None
    voluntario.email = email
    voluntario.direccion = direccion or None
    voluntario.ciudad = ciudad or None
    voluntario.provincia = provincia or None
    voluntario.codigo_postal = codigo_postal or None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "El DNI o email ya está en uso por otro voluntario.", "danger")
        return RedirectResponse(f"/voluntarios/{voluntario_id}/editar-datos", status_code=303)
    flash(request, "Datos actualizados correctamente.")
    return RedirectResponse(f"/voluntarios/{voluntario_id}", status_code=303)
