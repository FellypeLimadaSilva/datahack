-- =============================================================================
-- SEED DEMONSTRATIVO · dados SINTÉTICOS, determinísticos, SEM validade oficial.
-- Serve só para ver o dashboard funcionando antes dos dados reais do INEP.
-- Para os dados reais: rode 10_marts_from_staging.sql (ele faz TRUNCATE nos mart.*).
-- =============================================================================
CREATE FUNCTION pg_temp.r(seed text) RETURNS numeric LANGUAGE sql IMMUTABLE AS
$$ SELECT (abs(hashtext(seed)) % 10000) / 10000.0 $$;

TRUNCATE mart.trajetoria, mart.censo_curso, mart.cpc_curso,
         mart.licenciatura_curso, mart.oferta_municipio, mart.qualidade_checks;

-- Catálogos ------------------------------------------------------------------------
CREATE TEMP TABLE _rot(nome text, area text, grau text, tda10 numeric);
INSERT INTO _rot VALUES
 ('Direito','Negócios, administração e direito','Bacharelado',38),
 ('Administração','Negócios, administração e direito','Bacharelado',52),
 ('Ciências contábeis','Negócios, administração e direito','Bacharelado',50),
 ('Enfermagem','Saúde e bem-estar','Bacharelado',33),
 ('Medicina','Saúde e bem-estar','Bacharelado',9),
 ('Psicologia','Saúde e bem-estar','Bacharelado',35),
 ('Educação física','Saúde e bem-estar','Bacharelado',44),
 ('Pedagogia','Educação','Licenciatura',47),
 ('Matemática','Educação','Licenciatura',63),
 ('Letras – Português','Educação','Licenciatura',58),
 ('História','Educação','Licenciatura',52),
 ('Ciências biológicas','Educação','Licenciatura',55),
 ('Geografia','Educação','Licenciatura',54),
 ('Física','Educação','Licenciatura',66),
 ('Agronomia','Agricultura, silvicultura, pesca e veterinária','Bacharelado',36),
 ('Zootecnia','Agricultura, silvicultura, pesca e veterinária','Bacharelado',49),
 ('Engenharia civil','Engenharia, produção e construção','Bacharelado',55),
 ('Sistemas de informação','Computação e TIC','Bacharelado',61),
 ('Análise e desenvolvimento de sistemas','Computação e TIC','Tecnológico',58);

CREATE TEMP TABLE _ies(co text, nome text, cat text, rede text);
INSERT INTO _ies VALUES
 ('1','IES Demo 01 (federal)','Pública federal','Pública'),
 ('2','IES Demo 02 (estadual)','Pública estadual','Pública'),
 ('3','IES Demo 03 (federal)','Pública federal','Pública'),
 ('4','IES Demo 04 (privada)','Privada com fins lucrativos','Privada'),
 ('5','IES Demo 05 (privada)','Privada com fins lucrativos','Privada'),
 ('6','IES Demo 06 (privada)','Privada sem fins lucrativos','Privada'),
 ('7','IES Demo 07 (privada)','Privada sem fins lucrativos','Privada'),
 ('8','IES Demo 08 (privada)','Privada com fins lucrativos','Privada');

CREATE TEMP TABLE _mun(co text, nome text);
INSERT INTO _mun VALUES
 ('5103403','Cuiabá'),('5108402','Várzea Grande'),('5107602','Rondonópolis'),('5107909','Sinop'),
 ('5107958','Tangará da Serra'),('5102504','Cáceres'),('5101803','Barra do Garças'),('5107925','Sorriso');

-- Cursos ofertados (curso × IES × município × modalidade), escolhidos por hash ----------
CREATE TEMP TABLE _cur AS
SELECT row_number() OVER (ORDER BY r.nome, i.co, m.co, md.mod)::text AS co_curso,
       r.nome, r.area, r.grau, r.tda10, i.co AS co_ies, i.nome AS no_ies, i.cat, i.rede,
       m.co AS co_mun, m.nome AS mun, md.mod
FROM _rot r CROSS JOIN _ies i CROSS JOIN _mun m CROSS JOIN (VALUES ('Presencial'),('EAD')) md(mod)
WHERE pg_temp.r(r.nome||i.co||m.co||md.mod) < CASE
        WHEN md.mod = 'EAD' THEN (CASE WHEN i.rede = 'Privada' AND m.co IN ('5103403','5107602','5107909') THEN 0.22 ELSE 0 END)
        WHEN i.rede = 'Pública' THEN (CASE WHEN m.co IN ('5103403','5107602','5107909','5102504') THEN 0.55 ELSE 0.12 END)
        ELSE (CASE WHEN m.co IN ('5103403','5108402','5107602','5107909') THEN 0.45 ELSE 0.10 END) END;

-- Trajetória (coortes 2015–2020, até 2024) ------------------------------------------------
CREATE TEMP TABLE _sd(k int, f numeric); INSERT INTO _sd VALUES (1,.22),(2,.45),(3,.62),(4,.74),(5,.83),(6,.89),(7,.94),(8,.97),(9,.99),(10,1);
CREATE TEMP TABLE _sc(k int, f numeric); INSERT INTO _sc VALUES (1,0),(2,0),(3,0),(4,.05),(5,.34),(6,.66),(7,.85),(8,.94),(9,.98),(10,1);

CREATE TEMP TABLE _tr AS
SELECT c.*, co.coorte, (2024 - co.coorte + 1) AS kmax,
       greatest(12, round(30 + pg_temp.r(c.co_curso||co.coorte||'n') * 220 *
         CASE WHEN c.mod='EAD' THEN 2.2 WHEN c.rede='Pública' THEN 0.7 ELSE 1 END))::int AS n,
       least(85, greatest(4, c.tda10 * (1 + 0.025*(co.coorte-2015)) * (0.8 + pg_temp.r(c.co_curso||co.coorte||'d')*0.4)
         + CASE WHEN c.mod='EAD' THEN 8 ELSE 0 END)) AS tda_f,
       (30 + pg_temp.r(c.co_curso||'c')*22) AS tca_f
FROM _cur c CROSS JOIN generate_series(2015,2020) co(coorte);

INSERT INTO mart.trajetoria
SELECT t.coorte, t.coorte + s.k - 1, s.k, t.co_curso, t.nome, t.co_ies, t.no_ies, t.cat, t.rede, t.mod, t.grau, t.area, t.nome,
       t.co_mun, t.mun, t.n,
       round(t.tda_f * s.f, 2), round(t.tca_f * c.f, 2), round(100 - t.tda_f * s.f - t.tca_f * c.f, 2),
       round(t.tda_f * (s.f - coalesce(sp.f,0)), 2), round(t.tca_f * (c.f - coalesce(cp.f,0)), 2),
       t.n * t.tda_f * s.f / 100, t.n * t.tca_f * c.f / 100, t.n * (100 - t.tda_f * s.f - t.tca_f * c.f) / 100,
       t.n * t.tda_f * (s.f - coalesce(sp.f,0)) / 100
FROM _tr t
JOIN _sd s  ON s.k <= t.kmax
JOIN _sc c  ON c.k = s.k
LEFT JOIN _sd sp ON sp.k = s.k - 1
LEFT JOIN _sc cp ON cp.k = s.k - 1;

-- Censo 2021–2024 (anomalia proposital: salto de 2023 no EAD privado) ----------------------
INSERT INTO mart.censo_curso
SELECT y.ano, c.co_curso, c.nome, c.co_ies, c.no_ies, c.cat, c.rede, c.mod, c.grau, c.area, c.nome, c.co_mun, c.mun,
       v.vagas, v.ing, v.mat, round(v.mat * 0.14), round(v.mat * v.ev), round(v.mat * 0.02), round(v.mat * 0.03), 0,
       CASE WHEN c.rede='Privada' THEN round(v.ing * (0.02 + pg_temp.r(c.co_curso||'f')*0.30)) ELSE 0 END,
       CASE WHEN c.rede='Privada' THEN round(v.ing * (0.05 + pg_temp.r(c.co_curso||'p')*0.35)) ELSE 0 END,
       CASE WHEN c.rede='Privada' THEN round(v.mat * (0.02 + pg_temp.r(c.co_curso||'f')*0.30)) ELSE 0 END,
       CASE WHEN c.rede='Privada' THEN round(v.mat * (0.05 + pg_temp.r(c.co_curso||'p')*0.35)) ELSE 0 END
FROM _cur c CROSS JOIN generate_series(2021,2024) y(ano)
CROSS JOIN LATERAL (
  SELECT round((60 + pg_temp.r(c.co_curso||'v') * 200) * CASE WHEN c.mod='EAD' THEN 2.5 ELSE 1 END)::int AS vagas,
         round((40 + pg_temp.r(c.co_curso||y.ano||'i') * 160) * CASE WHEN c.mod='EAD' THEN 2.5 ELSE 1 END
               * CASE WHEN c.mod='EAD' AND c.rede='Privada' AND y.ano >= 2023 THEN 1.8 ELSE 1 END)::int AS ing,
         round((180 + pg_temp.r(c.co_curso||y.ano||'m') * 700) * CASE WHEN c.mod='EAD' THEN 2.5 ELSE 1 END
               * CASE WHEN c.mod='EAD' AND c.rede='Privada' AND y.ano >= 2023 THEN 1.6 ELSE 1 END)::int AS mat,
         (CASE WHEN c.rede='Pública' THEN 0.08 ELSE 0.17 END) * (0.8 + pg_temp.r(c.co_curso||y.ano||'e')*0.4)
           * CASE WHEN c.mod='EAD' THEN 1.35 ELSE 1 END
           * CASE WHEN y.ano = 2022 AND c.rede='Privada' THEN 1.12 ELSE 1 END AS ev
) v;

-- CPC (cada área cai numa edição do ciclo) ---------------------------------------------------
INSERT INTO mart.cpc_curso
SELECT y.ano, y.ano - 3, c.co_curso, c.nome, upper(c.nome), c.area, c.no_ies, c.cat, c.rede, c.mod, c.mun,
       f.faixa, round(f.cont, 3), t.qt_ingressante, t.n_desist, t.tda
FROM _cur c
JOIN LATERAL (SELECT 2021 + (abs(hashtext(c.area)) % 3) AS ano) y ON true
JOIN LATERAL (SELECT pg_temp.r(c.co_curso||'cpc') AS x) rr ON true
JOIN LATERAL (SELECT CASE WHEN rr.x < .10 THEN 'Sem CPC' WHEN rr.x < .13 THEN 'CPC 1' WHEN rr.x < .30 THEN 'CPC 2'
                          WHEN rr.x < .68 THEN 'CPC 3' WHEN rr.x < .93 THEN 'CPC 4' ELSE 'CPC 5' END AS faixa,
                     CASE WHEN rr.x < .10 THEN NULL ELSE 0.6 + rr.x * 4.2 END AS cont) f ON true
LEFT JOIN mart.trajetoria t ON t.co_curso = c.co_curso AND t.coorte = y.ano - 3 AND t.ano_ref = y.ano;

-- Licenciaturas (coorte 2015 em 2024 + Enade 2025) -----------------------------------------------
INSERT INTO mart.licenciatura_curso
SELECT 2015, t.co_curso, t.no_curso, upper(t.rotulo_cine), t.no_ies, t.categoria_adm, t.rede, t.modalidade, t.municipio,
       t.qt_ingressante, t.n_desist, t.tda,
       p.part, round(p.part * q.pct / 100), q.pct,
       CASE WHEN q.pct < 25 THEN '2' WHEN q.pct < 40 THEN '3' WHEN q.pct < 55 THEN '4' ELSE '5' END
FROM mart.trajetoria t
JOIN LATERAL (SELECT round(t.qt_ingressante * (0.35 + pg_temp.r(t.co_curso||'pp') * 0.35))::int AS part) p ON true
JOIN LATERAL (SELECT round((15 + pg_temp.r(t.co_curso||'pc') * 55)::numeric, 1) AS pct) q ON true
WHERE t.coorte = 2015 AND t.ano_ref = 2024 AND t.grau = 'Licenciatura';

-- Desertos: 8 municípios reais com oferta + 134 genéricos (≈72% sem oferta) ----------------------
INSERT INTO mart.oferta_municipio
SELECT m.co, m.nome, x.tot, x.pub, x.priv, p.pop::int,
       round(x.tot * 100.0 / p.pop, 2),
       CASE WHEN x.tot = 0 THEN '1. Sem oferta' WHEN x.tot * 100.0 / p.pop < 5 THEN '2. Até 5'
            WHEN x.tot * 100.0 / p.pop < 15 THEN '3. 5–15' WHEN x.tot * 100.0 / p.pop < 30 THEN '4. 15–30'
            ELSE '5. Mais de 30' END
FROM (SELECT co, nome, true AS real FROM _mun
      UNION ALL SELECT '51'||lpad(g::text,5,'0'), 'Município demo '||lpad(g::text,3,'0'), false FROM generate_series(1,134) g) m
JOIN LATERAL (SELECT CASE WHEN m.co = '5103403' THEN 95000 ELSE round(2500 + pg_temp.r(m.co||'pop') * 38000) END AS pop) p ON true
JOIN LATERAL (
  SELECT CASE WHEN m.real THEN coalesce(sum(qt_vagas),0)::int
              WHEN pg_temp.r(m.co||'of') < 0.28 THEN round(40 + pg_temp.r(m.co||'vg') * 600)::int ELSE 0 END AS tot,
         CASE WHEN m.real THEN coalesce(sum(qt_vagas) FILTER (WHERE rede='Pública'),0)::int
              ELSE 0 END AS pub,
         CASE WHEN m.real THEN coalesce(sum(qt_vagas) FILTER (WHERE rede='Privada'),0)::int
              WHEN pg_temp.r(m.co||'of') < 0.28 THEN round(40 + pg_temp.r(m.co||'vg') * 600)::int ELSE 0 END AS priv
  FROM mart.censo_curso WHERE ano = 2024 AND modalidade = 'Presencial' AND co_municipio = m.co) x ON true;

INSERT INTO mart.qualidade_checks VALUES
 ('seed','Dados SINTÉTICOS carregados pelo 90_demo_seed.sql',NULL,'trocar pelos dados reais',false);
