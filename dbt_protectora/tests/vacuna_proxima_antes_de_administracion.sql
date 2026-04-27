-- Falla si hay vacunas donde la próxima dosis es anterior a la fecha de administración
select
    v.id,
    p.nombre as perro,
    v.tipo,
    v.fecha_administracion,
    v.fecha_proxima
from {{ ref('stg_vacunas') }} v
join {{ ref('stg_perros') }} p on v.perro_id = p.id
where v.fecha_proxima is not null
  and v.fecha_proxima < v.fecha_administracion
