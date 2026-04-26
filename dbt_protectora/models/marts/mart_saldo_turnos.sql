with voluntarios as (
    select * from {{ ref('stg_voluntarios') }}
),

turnos as (
    select
        voluntario_id,
        sum(case
            when estado = 'realizado'   then 1.0
            when estado = 'medio_turno' then 0.5
            else 0.0
        end) as turnos_acumulados,
        count(*) filter (where estado = 'realizado')          as n_realizados,
        count(*) filter (where estado = 'medio_turno')        as n_medios,
        count(*) filter (where estado = 'falta_justificada')  as n_faltas_justificadas,
        count(*) filter (where estado = 'falta_injustificada') as n_faltas_injustificadas,
        count(*) filter (where estado = 'no_apuntado')        as n_no_apuntados
    from {{ ref('stg_turnos_voluntarios') }}
    group by voluntario_id
)

select
    v.id,
    v.nombre,
    v.apellido,
    v.perfil,
    v.fecha_alta,
    v.activo,
    (current_date - GREATEST(v.fecha_alta, DATE '2026-04-01')) / 7                        as semanas_activo,
    coalesce(t.turnos_acumulados, 0)                                                      as turnos_acumulados,
    coalesce(t.turnos_acumulados, 0) - (current_date - GREATEST(v.fecha_alta, DATE '2026-04-01')) / 7 as saldo,
    coalesce(t.n_realizados, 0)                                   as n_realizados,
    coalesce(t.n_medios, 0)                                       as n_medios,
    coalesce(t.n_faltas_justificadas, 0)                          as n_faltas_justificadas,
    coalesce(t.n_faltas_injustificadas, 0)                        as n_faltas_injustificadas,
    coalesce(t.n_no_apuntados, 0)                                 as n_no_apuntados
from voluntarios v
left join turnos t on v.id = t.voluntario_id
order by saldo asc
