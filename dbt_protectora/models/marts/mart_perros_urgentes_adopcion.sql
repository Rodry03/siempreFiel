with urgentes as (
    select
        p.id,
        p.nombre,
        r.nombre                                                              as raza,
        p.sexo,
        p.ppp,
        p.esterilizado,
        p.fecha_entrada,
        current_date - p.fecha_entrada                                        as dias_en_refugio,
        date_part('year', age(current_date, p.fecha_nacimiento))              as edad_anios
    from {{ source('protectora', 'perros') }} p
    left join {{ source('protectora', 'razas') }} r on r.id = p.raza_id
    inner join {{ source('protectora', 'ubicaciones') }} u
        on u.perro_id = p.id and u.fecha_fin is null and u.tipo = 'refugio'
    where p.estado in ('libre', 'reservado')
      and p.fecha_entrada is not null
)

select * from urgentes
order by dias_en_refugio desc
