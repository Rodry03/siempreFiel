with perros as (
    select fecha_entrada
    from {{ source('protectora', 'perros') }}
    where fecha_entrada is not null
      and fecha_entrada >= date_trunc('month', current_date - interval '2 years')
),

por_mes as (
    select
        date_trunc('month', fecha_entrada)::date as mes,
        count(*)                                  as total_entradas
    from perros
    group by date_trunc('month', fecha_entrada)
)

select
    mes,
    total_entradas,
    to_char(mes, 'Mon YYYY') as mes_label
from por_mes
order by mes
