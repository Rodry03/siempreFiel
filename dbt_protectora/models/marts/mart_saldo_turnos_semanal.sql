with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('" ~ var('fecha_inicio_turnos') ~ "' as date)",
        end_date="cast(current_date + interval '1 day' as date)"
    ) }}
),

semanas as (
    select distinct date_trunc('week', date_day::timestamp)::date as semana
    from spine
),

voluntarios as (
    select * from {{ ref('stg_voluntarios') }}
    where perfil not in ('directiva', 'guagua', 'eventos', 'colaboradores')
),

turnos as (
    select * from {{ ref('stg_turnos_voluntarios') }}
),

apoyo_semanas as (
    select
        pa.voluntario_id,
        s.semana,
        bool_or(
            pa.fecha_inicio <= (s.semana + interval '6 days')::date
            and (pa.fecha_fin is null or pa.fecha_fin >= s.semana)
        ) as en_apoyo
    from {{ source('protectora', 'periodos_apoyo') }} pa
    cross join semanas s
    group by pa.voluntario_id, s.semana
),

turnos_por_semana as (
    select
        voluntario_id,
        semana,
        sum(case
            when estado = 'realizado'   then 1.0
            when estado = 'medio_turno' then 0.5
            else 0.0
        end) as valor
    from turnos
    group by voluntario_id, semana
),

grid as (
    select
        v.id            as voluntario_id,
        v.nombre,
        v.apellido,
        v.perfil,
        s.semana
    from voluntarios v
    cross join semanas s
    where s.semana >= greatest(
        date_trunc('week', coalesce(v.fecha_veterano, v.fecha_alta)::timestamp)::date,
        date_trunc('week', cast('{{ var("fecha_inicio_turnos") }}' as timestamp))::date
    )
),

resultado as (
    select
        g.voluntario_id,
        g.nombre,
        g.apellido,
        g.perfil,
        g.semana,
        coalesce(t.valor, 0)                                        as turnos_semana,
        case
            when coalesce(ap.en_apoyo, false) then 0.0
            else coalesce(t.valor, 0) - 1.0
        end                                                         as saldo_semana,
        sum(case
            when coalesce(ap.en_apoyo, false) then 0.0
            else coalesce(t.valor, 0) - 1.0
        end) over (
            partition by g.voluntario_id
            order by g.semana
            rows between unbounded preceding and current row
        )                                                           as saldo_acumulado
    from grid g
    left join turnos_por_semana t
        on t.voluntario_id = g.voluntario_id
       and t.semana = g.semana
    left join apoyo_semanas ap
        on ap.voluntario_id = g.voluntario_id
       and ap.semana = g.semana
)

select * from resultado
order by voluntario_id, semana
