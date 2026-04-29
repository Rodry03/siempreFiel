with adoptados as (
    select
        p.id,
        p.fecha_entrada,
        u.fecha_inicio                                                        as fecha_adopcion,
        date_trunc('month', u.fecha_inicio)::date                            as mes,
        (u.fecha_inicio - p.fecha_entrada)                                   as dias_hasta_adopcion
    from {{ source('protectora', 'perros') }} p
    inner join {{ source('protectora', 'ubicaciones') }} u
        on u.perro_id = p.id
       and u.tipo = 'adoptado'
    where p.estado = 'adoptado'
      and p.fecha_entrada is not null
      and u.fecha_inicio >= p.fecha_entrada
      and u.fecha_inicio >= date_trunc('month', current_date - interval '1 year')
)

select
    mes,
    to_char(mes, 'Mon YYYY')              as mes_label,
    round(avg(dias_hasta_adopcion))       as dias_medio,
    count(*)                              as total_adopciones
from adoptados
group by mes
order by mes
