select
    id,
    perro_id,
    tipo,
    fecha_administracion,
    fecha_proxima,
    veterinario,
    notas
from {{ source('protectora', 'vacunas') }}
