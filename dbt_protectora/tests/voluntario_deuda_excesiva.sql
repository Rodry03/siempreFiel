-- Falla si hay voluntarios con un saldo menor de -10 turnos
select
    id,
    nombre,
    apellido,
    saldo
from {{ ref('mart_saldo_turnos') }}
where saldo < -30
