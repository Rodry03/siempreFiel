with source as (
    select * from {{ source('raw', 'perros_xlsx') }}
),

limpio as (
    select
        numero::int                                     as numero,
        trim(perro)                                     as nombre,
        trim(regexp_replace(
            initcap(trim(
                case
                    when raza ilike '%stanfford%'   then regexp_replace(raza, '(?i)stanfford', 'Staffordshire')
                    when raza ilike '%andalux%'     then regexp_replace(raza, '(?i)andalux', 'Andaluz')
                    when raza ilike '%aleman%' and raza not ilike '%alemán%'
                                                    then regexp_replace(raza, '(?i)aleman', 'Alemán')
                    when raza ilike '%portugues%' and raza not ilike '%portugués%'
                                                    then regexp_replace(raza, '(?i)portugues', 'Portugués')
                    else raza
                end
            )),
            '\s*\(Ppp\)|\s+Ppp$', '', 'gi'
        ))                                              as raza,
        lower(sexo)                                     as sexo,
        castrado = 'SI'                                 as esterilizado,
        num_chip                                        as num_chip,
        num_pasaporte                                   as num_pasaporte,
        case when fec_nacimiento ~ '^\d{4}-\d{2}-\d{2}' then fec_nacimiento::date end as fecha_nacimiento,
        f_entrada::date                                 as fecha_entrada,
        f_salida::date                                  as fecha_salida,
        trim(lower(estado))                             as tipo_ubicacion,
        capa                                            as color,
        trim(observaciones)                             as notas,

        -- Vacunas: solo convertimos valores en formato YYYY-MM-DD (como los guarda pandas)
        case when rabia ~ '^\d{4}-\d{2}-\d{2}' then rabia::date end         as vacuna_rabia,
        case when recor_rabia ~ '^\d{4}-\d{2}-\d{2}' then recor_rabia::date end as proxima_rabia,
        case when canigen ~ '^\d{4}-\d{2}-\d{2}' then canigen::date end      as vacuna_canigen,
        case when recor_canigen ~ '^\d{4}-\d{2}-\d{2}' then recor_canigen::date end as proxima_canigen,
        case when dps_inter ~ '^\d{4}-\d{2}-\d{2}' then dps_inter::date end  as vacuna_dps,
        case when recor_dps ~ '^\d{4}-\d{2}-\d{2}' then recor_dps::date end  as proxima_dps

    from source
)

select * from limpio
