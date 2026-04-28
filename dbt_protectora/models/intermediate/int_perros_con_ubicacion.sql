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
    p.sexo,
    p.esterilizado,
    p.num_chip,
    p.color,
    p.fecha_nacimiento,
    p.fecha_entrada,
    p.estado,
    p.notas,
    date_part('year', age(p.fecha_nacimiento))::int as edad_anios,
    (current_date - p.fecha_entrada)::int           as dias_en_sistema,
    u.ubicacion                                      as ubicacion_actual
from perros p
left join ubicacion_actual u on p.id = u.perro_id
