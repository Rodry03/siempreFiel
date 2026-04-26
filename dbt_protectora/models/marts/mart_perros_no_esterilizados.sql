-- Perros activos que todavía no están esterilizados
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
    p.fecha_nacimiento,
    date_part('year', age(p.fecha_nacimiento))::int as edad_anios,
    u.ubicacion as ubicacion_actual
from perros p
left join ubicacion_actual u on p.id = u.perro_id
where p.esterilizado = false
order by p.fecha_nacimiento asc nulls last
