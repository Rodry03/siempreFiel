with perros as (
    select * from {{ ref('stg_perros') }}
),

ubicacion_actual as (
    {{ ubicacion_actual_perro() }}
)

select
    p.id,
    p.nombre,
    p.raza,
    p.fecha_entrada,
    (current_date - p.fecha_entrada)::int     as dias_en_sistema,
    u.ubicacion                                as ubicacion_actual
from perros p
left join ubicacion_actual u on p.id = u.perro_id
order by dias_en_sistema desc
