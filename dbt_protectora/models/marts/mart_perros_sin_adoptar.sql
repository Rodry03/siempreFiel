with activos as (
    select
        p.id,
        p.nombre,
        r.nombre                                                              as raza,
        p.sexo,
        p.ppp,
        p.esterilizado,
        p.fecha_entrada,
        current_date - p.fecha_entrada                                        as dias_en_refugio,
        date_part('year', age(current_date, p.fecha_nacimiento))              as edad_anios,
        case
            when date_part('year', age(current_date, p.fecha_nacimiento)) < 2 then 'joven'
            when date_part('year', age(current_date, p.fecha_nacimiento)) < 7 then 'adulto'
            else 'senior'
        end                                                                   as franja_edad,
        u.tipo                                                                as ubicacion_actual
    from {{ source('protectora', 'perros') }} p
    left join {{ source('protectora', 'razas') }} r on r.id = p.raza_id
    left join {{ source('protectora', 'ubicaciones') }} u
        on u.perro_id = p.id and u.fecha_fin is null
    where p.estado = 'libre'
      and p.fecha_entrada is not null
)

select
    *,
    case
        when dias_en_refugio > 180 then 'critico'
        when dias_en_refugio > 90  then 'atencion'
        else                            'normal'
    end as nivel_alerta
from activos
order by dias_en_refugio desc
