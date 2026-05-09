with semanas as (
    select distinct semana
    from {{ ref('stg_turnos_voluntarios') }}
    where semana >= date_trunc('month', current_date - interval '8 months')::date
),

dias_semana as (
    select
        s.semana,
        s.semana + (generate_series(0, 6) || ' day')::interval as fecha
    from semanas s
),

slots_esperados as (
    select
        ds.semana,
        ds.fecha,
        f.franja
    from dias_semana ds
    cross join (select 'manana' as franja union all select 'tarde') f
),

turnos_con_perfil as (
    select
        t.semana,
        t.fecha,
        t.franja,
        t.estado,
        v.perfil
    from {{ ref('stg_turnos_voluntarios') }} t
    inner join {{ ref('stg_voluntarios') }} v on v.id = t.voluntario_id
    where t.semana >= date_trunc('month', current_date - interval '8 months')::date
),

por_slot as (
    select
        se.semana,
        se.fecha,
        se.franja,
        max(case when tcp.perfil in ('veterano', 'apoyo_en_junta') and tcp.estado in ('realizado', 'medio_turno') then 1 else 0 end) as tiene_veterano,
        max(case when tcp.perfil = 'voluntario'                   and tcp.estado in ('realizado', 'medio_turno') then 1 else 0 end) as tiene_voluntario
    from slots_esperados se
    left join turnos_con_perfil tcp on se.semana = tcp.semana
                                    and se.fecha = tcp.fecha
                                    and se.franja = tcp.franja
    group by se.semana, se.fecha, se.franja
),

por_semana as (
    select
        semana,
        sum(case when tiene_veterano = 1 then 1 else 0 end)                                as slots_con_veterano,
        sum(case when tiene_veterano = 1 and tiene_voluntario = 1 then 1 else 0 end)      as slots_completos
    from por_slot
    group by semana
)

select
    semana,
    to_char(semana, 'DD Mon YYYY')                                    as semana_label,
    slots_con_veterano,
    slots_completos,
    14 - slots_con_veterano                                           as slots_sin_cubrir,
    14                                                                as slots_esperados,
    round(slots_con_veterano::numeric / 14 * 100, 1)                 as pct_con_veterano,
    round(slots_completos::numeric    / 14 * 100, 1)                 as pct_completos,
    case
        when 14 - slots_con_veterano > 0  then 'critico'
        when slots_completos         < 11 then 'bajo'
        else                               'ok'
    end                                                               as nivel
from por_semana
order by semana desc
