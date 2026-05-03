{{ config(materialized='view') }}

with perros as (
    select * from {{ ref('int_perros_con_ubicacion') }}
)

select
    id,
    nombre,
    raza,
    sexo,
    fecha_nacimiento,
    edad_anios,
    ubicacion_actual
from perros
where esterilizado = false
order by fecha_nacimiento asc nulls last
