select
    id,
    nombre,
    apellido,
    email,
    telefono,
    perfil,
    fecha_alta,
    activo
from {{ source('protectora', 'voluntarios') }}
