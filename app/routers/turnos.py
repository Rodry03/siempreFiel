from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.auth import get_current_user, require_not_veterano
from app.database import get_db
from app.models import Voluntario, TurnoMensual, PerfilVoluntario
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

FECHA_INICIO_TURNOS = date(2026, 5, 1)


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
    # Si hay saldo manual, usarlo; si no, calcular
    if voluntario.saldo_manual is not None:
        return voluntario.saldo_manual
    fecha_inicio = max(FECHA_INICIO_TURNOS, voluntario.fecha_alta)
    semanas_activo = (date.today() - fecha_inicio).days // 7
    # Solo contar turnos a partir de FECHA_INICIO_TURNOS
    turnos_acumulados = sum(t.turnos for t in voluntario.turnos_mensuales if t.mes >= FECHA_INICIO_TURNOS)
    return voluntario.deuda_inicial + turnos_acumulados - semanas_activo


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
    total_turnos = sum(t.turnos for t in voluntario.turnos_mensuales) if hace_turnos else 0
    tiempo_voluntario = calcular_tiempo_voluntario(voluntario.fecha_alta)

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

    return templates.TemplateResponse(request, "voluntarios/detail.html", {
        "voluntario": voluntario,
        "hace_turnos": hace_turnos,
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
        "meses_es": MESES_ES,
    })
