-- =============================================================================
-- staging -> mart  (rodar DEPOIS de 00_marts_ddl.sql e da ingestão)
-- Idempotente: TRUNCATE + INSERT; rodar duas vezes dá as mesmas contagens.
--
-- PRESSUPOSTOS sobre o staging (ajuste os nomes ao seu pipeline, o resto é igual):
--   Colunas = nomes originais do INEP em minúsculas; CÓDIGOS COMO TEXTO.
--   stg.trajetoria          1 linha = curso × coorte × ano de referência (6 coortes empilhadas)
--   stg.censo_cursos        MICRODADOS_CADASTRO_CURSOS 2021–2024 empilhados (coluna nu_ano_censo)
--   stg.cpc                 CPC 2021–2023 empilhados; colunas: ano, codigo_do_curso, area_de_avaliacao,
--                           cpc_continuo, cpc_faixa  ('1'..'5' ou 'SC')
--   stg.enade_licenciaturas codigo_do_curso, area_de_avaliacao, n_de_concluintes_participantes,
--                           total_igual_ou_acima_padrao1, percentual_igual_ou_acima_padrao1 (0–1),
--                           conceito_enade_faixa
--   stg.ibge_pop_18_24      co_municipio, municipio, pop_18_24  (soma das idades 18..24 da tabela 9514)
-- ESCALA das taxas: TDA/TCA/TAP vêm em 0–100? Se vierem em 0–1, troque 1.0 por 100.0 abaixo.
-- =============================================================================
BEGIN;

TRUNCATE mart.trajetoria, mart.censo_curso, mart.cpc_curso,
         mart.licenciatura_curso, mart.oferta_municipio, mart.qualidade_checks;

-- Dimensões de rótulo ----------------------------------------------------------
CREATE TEMP TABLE _cfg AS SELECT 1.0::numeric AS escala;

CREATE TEMP TABLE _mun AS
SELECT DISTINCT ON (co_municipio::text) co_municipio::text AS co_municipio, no_municipio AS municipio
FROM stg.censo_cursos WHERE co_uf::text = '51' AND co_municipio IS NOT NULL;

CREATE FUNCTION pg_temp.f_rede(cat int) RETURNS text LANGUAGE sql IMMUTABLE AS
$$ SELECT CASE WHEN cat IN (1,2,3) THEN 'Pública' WHEN cat IN (4,5) THEN 'Privada' ELSE 'Especial' END $$;
CREATE FUNCTION pg_temp.f_cat(cat int) RETURNS text LANGUAGE sql IMMUTABLE AS
$$ SELECT CASE cat WHEN 1 THEN 'Pública federal' WHEN 2 THEN 'Pública estadual' WHEN 3 THEN 'Pública municipal'
                   WHEN 4 THEN 'Privada com fins lucrativos' WHEN 5 THEN 'Privada sem fins lucrativos' ELSE 'Especial' END $$;
CREATE FUNCTION pg_temp.f_mod(m int) RETURNS text LANGUAGE sql IMMUTABLE AS
$$ SELECT CASE m WHEN 1 THEN 'Presencial' WHEN 2 THEN 'EAD' END $$;
CREATE FUNCTION pg_temp.f_grau(g int) RETURNS text LANGUAGE sql IMMUTABLE AS
$$ SELECT CASE g WHEN 1 THEN 'Bacharelado' WHEN 2 THEN 'Licenciatura' WHEN 3 THEN 'Tecnológico' END $$;

-- P1/P2 · Trajetória (MT) ------------------------------------------------------
INSERT INTO mart.trajetoria
SELECT t.nu_ano_ingresso::int, t.nu_ano_referencia::int, t.nu_ano_referencia::int - t.nu_ano_ingresso::int + 1,
       t.co_curso::text, t.no_curso, t.co_ies::text, t.no_ies,
       pg_temp.f_cat(t.tp_categoria_administrativa::int), pg_temp.f_rede(t.tp_categoria_administrativa::int),
       pg_temp.f_mod(t.tp_modalidade_ensino::int), pg_temp.f_grau(t.tp_grau_academico::int),
       t.no_cine_area_geral, t.no_cine_rotulo, t.co_municipio::text, m.municipio,
       t.qt_ingressante::int,
       t.tda::numeric * c.escala, t.tca::numeric * c.escala, t.tap::numeric * c.escala,
       t.tada::numeric * c.escala, t.tcan::numeric * c.escala,
       t.tda::numeric * c.escala / 100 * t.qt_ingressante,
       t.tca::numeric * c.escala / 100 * t.qt_ingressante,
       t.tap::numeric * c.escala / 100 * t.qt_ingressante,
       t.tada::numeric * c.escala / 100 * t.qt_ingressante
FROM stg.trajetoria t CROSS JOIN _cfg c
LEFT JOIN _mun m ON m.co_municipio = t.co_municipio::text
WHERE t.co_uf::text = '51' AND t.qt_ingressante IS NOT NULL;

-- P3/B2 · Censo (graduação, MT; EAD por polo em MT) ---------------------------------
INSERT INTO mart.censo_curso
SELECT s.nu_ano_censo::int, s.co_curso::text, max(s.no_curso), max(s.co_ies::text), max(s.no_ies),
       pg_temp.f_cat(max(s.tp_categoria_administrativa::int)), pg_temp.f_rede(max(s.tp_categoria_administrativa::int)),
       pg_temp.f_mod(max(s.tp_modalidade_ensino::int)), pg_temp.f_grau(max(s.tp_grau_academico::int)),
       max(s.no_cine_area_geral), max(s.no_cine_rotulo), s.co_municipio::text, max(s.no_municipio),
       sum(coalesce(s.qt_vg_total::int,0)), sum(coalesce(s.qt_ing::int,0)), sum(coalesce(s.qt_mat::int,0)),
       sum(coalesce(s.qt_conc::int,0)), sum(coalesce(s.qt_sit_desvinculado::int,0)),
       sum(coalesce(s.qt_sit_transferido::int,0)), sum(coalesce(s.qt_sit_trancada::int,0)),
       sum(coalesce(s.qt_sit_falecido::int,0)), sum(coalesce(s.qt_ing_fies::int,0)),
       sum(coalesce(s.qt_ing_prounii::int,0) + coalesce(s.qt_ing_prounip::int,0)),
       sum(coalesce(s.qt_mat_fies::int,0)),
       sum(coalesce(s.qt_mat_prounii::int,0) + coalesce(s.qt_mat_prounip::int,0))
FROM stg.censo_cursos s
WHERE s.co_uf::text = '51' AND s.tp_nivel_academico::int = 1          -- só graduação
  AND s.tp_dimensao::int IN (1,2)                                     -- presencial BR + EAD com polo
GROUP BY s.nu_ano_censo, s.co_curso, s.co_municipio;

-- P4 · CPC × desistência (CPC do ano Y ↔ coorte Y-3, 4º ano do curso) --------------
INSERT INTO mart.cpc_curso
SELECT p.ano::int, p.ano::int - 3, p.codigo_do_curso::text, t.no_curso, p.area_de_avaliacao, t.area_cine,
       t.no_ies, t.categoria_adm, t.rede, t.modalidade, t.municipio,
       CASE WHEN p.cpc_faixa::text IN ('1','2','3','4','5') THEN 'CPC ' || p.cpc_faixa::text ELSE 'Sem CPC' END,
       p.cpc_continuo::numeric, t.qt_ingressante, t.n_desist, t.tda
FROM stg.cpc p
LEFT JOIN mart.trajetoria t
       ON t.co_curso = p.codigo_do_curso::text AND t.coorte = p.ano::int - 3 AND t.ano_ref = p.ano::int
WHERE p.sigla_da_uf = 'MT';

-- P5 · Licenciaturas: coorte 2015 em 2024 + Enade 2025 ------------------------------
INSERT INTO mart.licenciatura_curso
SELECT 2015, t.co_curso, t.no_curso, e.area_de_avaliacao, t.no_ies, t.categoria_adm, t.rede, t.modalidade,
       t.municipio, t.qt_ingressante, t.n_desist, t.tda,
       e.n_de_concluintes_participantes::int, e.total_igual_ou_acima_padrao1::int,
       e.percentual_igual_ou_acima_padrao1::numeric * 100, e.conceito_enade_faixa::text
FROM mart.trajetoria t
JOIN stg.enade_licenciaturas e ON e.codigo_do_curso::text = t.co_curso
WHERE t.coorte = 2015 AND t.ano_ref = 2024 AND t.grau = 'Licenciatura';

-- B1 · Desertos: base = os 142 municípios do IBGE (quem não tem curso entra com 0) ------
INSERT INTO mart.oferta_municipio
SELECT i.co_municipio::text, i.municipio,
       coalesce(v.tot,0), coalesce(v.pub,0), coalesce(v.priv,0), i.pop_18_24::int,
       round(coalesce(v.tot,0) * 100.0 / nullif(i.pop_18_24,0), 2),
       CASE WHEN coalesce(v.tot,0) = 0 THEN '1. Sem oferta'
            WHEN coalesce(v.tot,0) * 100.0 / i.pop_18_24 < 5  THEN '2. Até 5'
            WHEN coalesce(v.tot,0) * 100.0 / i.pop_18_24 < 15 THEN '3. 5–15'
            WHEN coalesce(v.tot,0) * 100.0 / i.pop_18_24 < 30 THEN '4. 15–30'
            ELSE '5. Mais de 30' END
FROM stg.ibge_pop_18_24 i
LEFT JOIN (SELECT co_municipio, sum(qt_vagas) tot,
                  sum(qt_vagas) FILTER (WHERE rede = 'Pública') pub,
                  sum(qt_vagas) FILTER (WHERE rede = 'Privada') priv
           FROM mart.censo_curso WHERE ano = 2024 AND modalidade = 'Presencial' GROUP BY co_municipio) v
       ON v.co_municipio = i.co_municipio::text;

-- Checagens ------------------------------------------------------------------------
INSERT INTO mart.qualidade_checks
SELECT 'trajetoria', 'coortes carregadas (esperado 6: 2015–2020)', count(DISTINCT coorte), '6', count(DISTINCT coorte) = 6 FROM mart.trajetoria
UNION ALL SELECT 'trajetoria', 'TAP+TCA+TDA ≈ 100 (linhas fora de 97–103)', count(*), '0',
       count(*) = 0 FROM mart.trajetoria WHERE (tap + tca + tda) NOT BETWEEN 97 AND 103
UNION ALL SELECT 'censo', 'anos carregados (esperado 4: 2021–2024)', count(DISTINCT ano), '4', count(DISTINCT ano) = 4 FROM mart.censo_curso
UNION ALL SELECT 'censo', 'chave duplicada ano×curso×município', count(*) - count(DISTINCT (ano, co_curso, co_municipio)), '0',
       count(*) = count(DISTINCT (ano, co_curso, co_municipio)) FROM mart.censo_curso
UNION ALL SELECT 'cpc', 'taxa de junção CPC → Trajetória (%)',
       round(100.0 * count(*) FILTER (WHERE qt_ingressante IS NOT NULL) / nullif(count(*),0), 1), '≥ 50 (explicar o resto)', NULL FROM mart.cpc_curso
UNION ALL SELECT 'licenciaturas', 'cursos com Enade 2025 casados com a Trajetória', count(*), '> 0', count(*) > 0 FROM mart.licenciatura_curso
UNION ALL SELECT 'oferta', 'municípios de MT (esperado 142)', count(*), '142', count(*) = 142 FROM mart.oferta_municipio
UNION ALL SELECT 'oferta', 'municípios sem oferta presencial', count(*) FILTER (WHERE vagas_pres = 0), 'informativo', NULL FROM mart.oferta_municipio;

COMMIT;
