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
),

turnos as (
    select * from {{ ref('stg_turnos_voluntarios') }}
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
        date_trunc('week', v.fecha_alta::timestamp)::date,
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
        coalesce(t.valor, 0)          as turnos_semana,
        coalesce(t.valor, 0) - 1      as saldo_semana,
        sum(coalesce(t.valor, 0) - 1) over (
            partition by g.voluntario_id
            order by g.semana
            rows between unbounded preceding and current row
        )                             as saldo_acumulado
    from grid g
    left join turnos_por_semana t
        on t.voluntario_id = g.voluntario_id
       and t.semana = g.semana
)

select * from resultado
order by voluntario_id, semana
