select
    date_trunc('month', fecha_contacto)::date           as mes,
    to_char(date_trunc('month', fecha_contacto), 'Mon YYYY') as mes_label,
    count(*)                                             as total_visitantes,
    count(*) filter (where estado = 'se_convirtio')      as convertidos,
    count(*) filter (where estado = 'descartado')        as descartados,
    round(
        count(*) filter (where estado = 'se_convirtio')::numeric
        / nullif(count(*), 0) * 100
    , 1)                                                 as tasa_conversion
from {{ source('protectora', 'visitantes') }}
where fecha_contacto >= date_trunc('month', current_date - interval '1 year')
group by date_trunc('month', fecha_contacto)
order by mes
