with adoptados as (
    select
        p.id,
        p.fecha_entrada,
        p.fecha_adopcion,
        date_trunc('month', p.fecha_adopcion)::date       as mes,
        (p.fecha_adopcion - p.fecha_entrada)              as dias_hasta_adopcion
    from {{ source('protectora', 'perros') }} p
    where p.estado = 'adoptado'
      and p.fecha_entrada is not null
      and p.fecha_adopcion is not null
      and p.fecha_adopcion >= p.fecha_entrada
      and p.fecha_adopcion >= date_trunc('month', current_date - interval '1 year')
)

select
    mes,
    to_char(mes, 'Mon YYYY')              as mes_label,
    round(avg(dias_hasta_adopcion))       as dias_medio,
    count(*)                              as total_adopciones
from adoptados
group by mes
order by mes
