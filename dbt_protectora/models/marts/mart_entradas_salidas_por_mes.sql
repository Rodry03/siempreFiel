with entradas as (
    select
        date_trunc('month', fecha_entrada)::date as mes,
        count(*)                                  as total_entradas
    from {{ source('protectora', 'perros') }}
    where fecha_entrada is not null
      and fecha_entrada >= date_trunc('month', current_date - interval '1 year')
    group by date_trunc('month', fecha_entrada)
),

salidas as (
    select
        date_trunc('month', fecha_inicio)::date as mes,
        count(*)                                 as total_salidas
    from {{ source('protectora', 'ubicaciones') }}
    where tipo = 'adoptado'
      and fecha_inicio >= date_trunc('month', current_date - interval '1 year')
    group by date_trunc('month', fecha_inicio)
),

meses as (
    select mes from entradas
    union
    select mes from salidas
)

select
    m.mes,
    to_char(m.mes, 'Mon YYYY')    as mes_label,
    coalesce(e.total_entradas, 0) as total_entradas,
    coalesce(s.total_salidas, 0)  as total_salidas
from meses m
left join entradas e on e.mes = m.mes
left join salidas  s on s.mes = m.mes
order by m.mes
