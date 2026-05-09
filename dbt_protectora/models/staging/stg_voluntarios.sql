select
    id,
    nombre,
    apellido,
    email,
    telefono,
    perfil,
    fecha_alta,
    fecha_veterano,
    activo
from {{ source('protectora', 'voluntarios') }}
