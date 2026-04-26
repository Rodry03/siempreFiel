-- Top 20 perros con más tiempo en el sistema desde su fecha de entrada
with perros as (
    select * from {{ ref('stg_perros') }}
),

ubicacion_actual as (
    select distinct on (perro_id)
        perro_id,
        tipo as ubicacion
    from {{ ref('stg_ubicaciones') }}
    where fecha_fin is null
    order by perro_id, fecha_inicio desc
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
limit 20
