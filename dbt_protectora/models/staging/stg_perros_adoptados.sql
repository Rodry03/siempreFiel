with source as (
    select * from {{ source('raw', 'perros_adoptados') }}
),

limpio as (
    select
        trim(perro)                                                         as nombre,
        lower(trim(sexo))                                                   as sexo,
        -- Chip: quitar espacios residuales
        nullif(trim(replace(num_chip::text, ' ', '')), '')                  as num_chip,
        nullif(trim(num_pasaporte::text), '')                               as num_pasaporte,
        case when fec_nacimiento ~ '^\d{4}-\d{2}-\d{2}'
             then fec_nacimiento::date end                                  as fecha_nacimiento,
        case when f_entrada ~ '^\d{4}-\d{2}-\d{2}'
             then f_entrada::date end                                       as fecha_entrada,
        -- Fecha de adopción: solo fechas válidas en formato YYYY-MM-DD
        case when f_salida ~ '^\d{4}-\d{2}-\d{2}'
             then f_salida::date end                                        as fecha_adopcion,

        -- Vacunas
        case when rabia ~ '^\d{4}-\d{2}-\d{2}' then rabia::date end        as vacuna_rabia,
        case when recor_rabia ~ '^\d{4}-\d{2}-\d{2}' then recor_rabia::date end as proxima_rabia,
        case when canigen ~ '^\d{4}-\d{2}-\d{2}' then canigen::date end     as vacuna_canigen,
        case when recor_canigen ~ '^\d{4}-\d{2}-\d{2}' then recor_canigen::date end as proxima_canigen,
        case when dps_inter ~ '^\d{4}-\d{2}-\d{2}' then dps_inter::date end as vacuna_dps,
        case when recor_dps ~ '^\d{4}-\d{2}-\d{2}' then recor_dps::date end as proxima_dps

    from source
    where trim(perro) is not null
      and lower(trim(sexo)) in ('macho', 'hembra')
)

select * from limpio
