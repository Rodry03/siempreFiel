-- Falla si hay perros activos sin ninguna ubicación registrada
select
    p.id,
    p.nombre
from {{ ref('stg_perros') }} p
left join {{ ref('stg_ubicaciones') }} u
    on u.perro_id = p.id and u.fecha_fin is null
where u.perro_id is null
