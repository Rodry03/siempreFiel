select
    date_trunc('month', fecha_fin)::date          as mes,
    to_char(date_trunc('month', fecha_fin), 'Mon YYYY') as mes_label,
    count(*)                                       as total_acogidas,
    round(avg(fecha_fin - fecha_inicio))           as dias_medio,
    min(fecha_fin - fecha_inicio)                  as dias_minimo,
    max(fecha_fin - fecha_inicio)                  as dias_maximo
from {{ source('protectora', 'ubicaciones') }}
where tipo = 'acogida'
  and fecha_fin is not null
  and fecha_inicio is not null
  and fecha_fin >= date_trunc('month', current_date - interval '1 year')
group by date_trunc('month', fecha_fin)
order by mes
