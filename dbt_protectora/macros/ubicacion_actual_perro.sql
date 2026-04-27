{% macro ubicacion_actual_perro() %}
    select distinct on (perro_id)
        perro_id,
        tipo as ubicacion
    from {{ ref('stg_ubicaciones') }}
    where fecha_fin is null
    order by perro_id, fecha_inicio desc
{% endmacro %}
