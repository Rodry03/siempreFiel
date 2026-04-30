with base as (
    select
        semana,
        fecha,
        franja,
        max(case when estado in ('realizado', 'medio_turno') then 1 else 0 end) as cubierto,
        sum(case when estado in ('falta_justificada', 'falta_injustificada') then 1 else 0 end) as faltas,
        count(*) as voluntarios_apuntados
    from {{ ref('stg_turnos_voluntarios') }}
    where semana >= date_trunc('month', current_date - interval '5 months')::date
    group by semana, fecha, franja
),

por_semana as (
    select
        semana,
        count(*)                                               as slots_registrados,
        sum(cubierto)                                          as slots_cubiertos,
        sum(faltas)                                            as total_faltas,
        sum(voluntarios_apuntados)                             as total_apuntados
    from base
    group by semana
)

select
    semana,
    to_char(semana, 'DD Mon YYYY')                             as semana_label,
    slots_cubiertos,
    14                                                         as slots_esperados,
    round(slots_cubiertos::numeric / 14 * 100, 1)             as pct_cobertura,
    total_faltas,
    total_apuntados,
    case
        when slots_cubiertos < 7  then 'critico'
        when slots_cubiertos < 11 then 'bajo'
        else                           'ok'
    end                                                        as nivel
from por_semana
order by semana desc
