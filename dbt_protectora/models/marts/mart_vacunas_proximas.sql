{{ config(materialized='view') }}

-- Perros con vacunas que vencen en los próximos 30 días (solo la dosis más reciente de cada tipo)
with vacunas_latest as (
    select distinct on (perro_id, tipo) *
    from {{ ref('stg_vacunas') }}
    order by perro_id, tipo, fecha_administracion desc
),

perros as (
    select * from {{ ref('stg_perros') }}
),

ubicacion_actual as (
    {{ ubicacion_actual_perro() }}
)

select
    p.id          as perro_id,
    p.nombre,
    p.raza,
    v.tipo        as vacuna,
    v.fecha_proxima,
    (v.fecha_proxima - current_date)::int as dias_restantes,
    u.ubicacion   as ubicacion_actual
from vacunas_latest v
join perros p on v.perro_id = p.id
left join ubicacion_actual u on p.id = u.perro_id
where v.fecha_proxima is not null
  and v.fecha_proxima <= current_date + interval '30 days'
order by v.fecha_proxima
