{{ config(materialized='table') }}

select
    id,
    voluntario_id,
    fecha,
    franja::text                                as franja,
    estado::text                                as estado,
    notas,
    date_trunc('week', fecha::timestamp)::date  as semana
from {{ source('protectora', 'turnos_voluntarios') }}
