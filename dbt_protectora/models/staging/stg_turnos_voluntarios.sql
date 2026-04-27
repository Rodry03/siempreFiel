{{ config(materialized='incremental', unique_key='id') }}

select
    id,
    voluntario_id,
    fecha,
    franja,
    estado,
    notas,
    date_trunc('week', fecha::timestamp)::date as semana
from {{ source('protectora', 'turnos_voluntarios') }}

{% if is_incremental() %}
    where fecha > (select max(fecha) from {{ this }})
{% endif %}
