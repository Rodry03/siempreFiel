select
    id,
    voluntario_id,
    fecha,
    franja,
    estado,
    notas,
    date_trunc('week', fecha::timestamp)::date as semana
from public.turnos_voluntarios
