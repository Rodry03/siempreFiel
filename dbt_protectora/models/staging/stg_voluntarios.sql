select
    id,
    nombre,
    apellido,
    email,
    telefono,
    perfil,
    fecha_alta,
    fecha_veterano,
    fecha_fin_veterano,
    activo
from {{ source('protectora', 'voluntarios') }}
