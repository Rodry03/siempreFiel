with perros as (
    select * from {{ ref('int_perros_con_ubicacion') }}
)

select
    id,
    nombre,
    raza,
    fecha_entrada,
    dias_en_sistema,
    ubicacion_actual
from perros
order by dias_en_sistema desc
