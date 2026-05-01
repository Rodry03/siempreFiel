with adoptados as (
    select
        p.id,
        p.sexo,
        p.ppp,
        p.esterilizado,
        p.fecha_entrada,
        p.fecha_nacimiento,
        p.fecha_adopcion,
        (p.fecha_adopcion - p.fecha_entrada)                                       as dias_hasta_adopcion,
        case
            when date_part('year', age(p.fecha_adopcion, p.fecha_nacimiento)) < 2 then 'joven'
            when date_part('year', age(p.fecha_adopcion, p.fecha_nacimiento)) < 7 then 'adulto'
            else 'senior'
        end                                                                        as franja_edad
    from {{ source('protectora', 'perros') }} p
    where p.estado = 'adoptado'
      and p.fecha_entrada is not null
      and p.fecha_adopcion is not null
      and p.fecha_adopcion >= p.fecha_entrada
),

por_sexo as (
    select
        'sexo'           as factor,
        sexo::text       as valor,
        round(avg(dias_hasta_adopcion)) as dias_medio,
        count(*)         as total
    from adoptados
    group by sexo
),

por_ppp as (
    select
        'ppp'                                          as factor,
        case when ppp then 'PPP' else 'No PPP' end     as valor,
        round(avg(dias_hasta_adopcion))                as dias_medio,
        count(*)                                       as total
    from adoptados
    group by ppp
),

por_franja as (
    select
        'franja_edad'    as factor,
        franja_edad      as valor,
        round(avg(dias_hasta_adopcion)) as dias_medio,
        count(*)         as total
    from adoptados
    group by franja_edad
),

por_esterilizado as (
    select
        'esterilizado'                                              as factor,
        case when esterilizado then 'Esterilizado' else 'Sin esterilizar' end as valor,
        round(avg(dias_hasta_adopcion))                            as dias_medio,
        count(*)                                                   as total
    from adoptados
    group by esterilizado
)

select * from por_sexo
union all
select * from por_ppp
union all
select * from por_franja
union all
select * from por_esterilizado
order by factor, dias_medio desc
