with turnos_agg as (
    select
        voluntario_id,
        sum(case when estado = 'realizado'           then 1.0 else 0 end)
        + sum(case when estado = 'medio_turno'       then 0.5 else 0 end) as turnos_realizados,
        sum(case when estado = 'falta_injustificada' then 1   else 0 end) as faltas_injustificadas
    from {{ ref('stg_turnos_voluntarios') }}
    group by voluntario_id
)

select
    v.id,
    v.nombre,
    v.apellido,
    v.perfil,
    (current_date - GREATEST(v.fecha_alta, DATE '{{ var("fecha_inicio_turnos") }}')) / 7  as semanas_activo,
    coalesce(t.turnos_realizados,     0)                                                   as turnos_realizados,
    coalesce(t.faltas_injustificadas, 0)                                                   as faltas_injustificadas,
    round(
        coalesce(t.turnos_realizados, 0)
        - (current_date - GREATEST(v.fecha_alta, DATE '{{ var("fecha_inicio_turnos") }}')) / 7
    , 1)                                                                                   as saldo
from {{ ref('stg_voluntarios') }} v
left join turnos_agg t on t.voluntario_id = v.id
where v.activo = true
  and v.perfil not in ('directiva', 'guagua', 'eventos', 'colaboradores')
order by saldo asc
