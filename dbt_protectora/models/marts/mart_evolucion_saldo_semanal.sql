select
    semana,
    to_char(semana, 'DD Mon YYYY')              as semana_label,
    round(avg(saldo_acumulado), 2)              as saldo_medio,
    count(*)                                    as n_voluntarios,
    count(*) filter (where saldo_acumulado < 0) as n_con_deuda
from {{ ref('mart_saldo_turnos_semanal') }}
where perfil not in ('directiva', 'guagua', 'eventos', 'colaboradores')
  and semana >= date_trunc('month', current_date - interval '8 months')::date
group by semana
order by semana
