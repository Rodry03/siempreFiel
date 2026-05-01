-- Perros bajo gestión de la protectora (libre o reservado)
select
    p.id,
    p.nombre,
    r.nombre as raza,
    p.fecha_nacimiento,
    p.sexo,
    p.esterilizado,
    p.num_chip,
    p.color,
    p.fecha_entrada,
    p.fecha_adopcion,
    p.estado,
    p.notas
from {{ source('protectora', 'perros') }} p
left join {{ source('protectora', 'razas') }} r on p.raza_id = r.id
where p.estado in ('libre', 'reservado')
