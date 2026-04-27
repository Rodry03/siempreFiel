with entrada as (
    select * from {{ ref('stg_perros_entrada') }}
),

razas_app as (
    select id as raza_id, nombre as raza_nombre
    from {{ source('protectora', 'razas') }}
),

perros_app as (
    select num_chip
    from {{ source('protectora', 'perros') }}
    where num_chip is not null
)

select
    e.numero,
    e.nombre,
    e.raza,
    r.raza_id,
    e.sexo,
    e.esterilizado,
    e.num_chip,
    e.num_pasaporte,
    e.fecha_nacimiento,
    e.fecha_entrada,
    e.tipo_ubicacion,
    e.color,
    e.notas,

    -- ¿La raza existe ya en la app?
    case when r.raza_id is not null then true else false end as raza_existe,

    -- ¿El perro ya está cargado en la app?
    case when p.num_chip is not null then true else false end as ya_en_app,

    -- Estado de carga
    case
        when p.num_chip is not null            then 'ya_cargado'
        when r.raza_id is null                 then 'pendiente_raza'
        when e.fecha_entrada is null           then 'pendiente_datos'
        else                                        'listo'
    end as estado_carga

from entrada e
left join razas_app r  on lower(trim(r.raza_nombre)) = lower(trim(e.raza))
left join perros_app p on p.num_chip = e.num_chip
order by estado_carga, e.nombre
