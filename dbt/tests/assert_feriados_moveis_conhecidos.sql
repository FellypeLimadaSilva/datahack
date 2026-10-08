with esperado(data, nome) as (
    values
        ('2024-03-31'::date, 'Páscoa'),
        ('2025-04-20'::date, 'Páscoa'),
        ('2026-04-05'::date, 'Páscoa'),
        ('2025-04-18'::date, 'Sexta-feira Santa'),
        ('2026-04-03'::date, 'Sexta-feira Santa'),
        ('2026-02-17'::date, 'Carnaval (terça-feira)'),
        ('2026-06-04'::date, 'Corpus Christi')
)
select e.*
from esperado e
left join {{ ref('dim_data') }} d on d.data = e.data and d.nome_feriado like '%' || e.nome || '%'
where d.data is null
