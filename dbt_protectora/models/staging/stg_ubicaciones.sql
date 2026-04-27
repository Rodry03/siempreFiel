select
    id,
    perro_id,
    tipo,
    fecha_inicio,
    fecha_fin,
    nombre_contacto,
    telefono_contacto,
    notas
from {{ source('protectora', 'ubicaciones') }}
