-- =============================================================================
-- Rota do Diploma · camada ANALÍTICA (mart) lida pelo Superset
-- Contrato entre o pipeline (ingestão/transformação) e o dashboard.
-- O Superset só lê o schema "mart". Nada de dado bruto ali.
-- Idempotente: pode rodar várias vezes (DROP ... CASCADE + CREATE).
-- Códigos (CO_CURSO, CO_IES, CO_MUNICIPIO) sempre como TEXTO.
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS mart;

DROP VIEW  IF EXISTS mart.financiamento_curso CASCADE;
DROP TABLE IF EXISTS mart.trajetoria          CASCADE;
DROP TABLE IF EXISTS mart.censo_curso         CASCADE;
DROP TABLE IF EXISTS mart.cpc_curso           CASCADE;
DROP TABLE IF EXISTS mart.licenciatura_curso  CASCADE;
DROP TABLE IF EXISTS mart.oferta_municipio    CASCADE;
DROP TABLE IF EXISTS mart.qualidade_checks    CASCADE;

-- -----------------------------------------------------------------------------
-- P1 / P2 · Trajetória (INEP). Grão: curso × coorte × ano de referência.
-- tda/tca/tap/tada/tcan em PONTOS PERCENTUAIS (0–100).
-- n_* = alunos estimados = taxa/100 × qt_ingressante (permite somar e ponderar).
-- Taxa de um grupo = SUM(n_*) / SUM(qt_ingressante) × 100  (média PONDERADA).
-- -----------------------------------------------------------------------------
CREATE TABLE mart.trajetoria (
  coorte          int      NOT NULL,   -- NU_ANO_INGRESSO
  ano_ref         int      NOT NULL,   -- NU_ANO_REFERENCIA
  ano_curso       int      NOT NULL,   -- ano_ref - coorte + 1
  co_curso        text     NOT NULL,
  no_curso        text,
  co_ies          text,
  no_ies          text,
  categoria_adm   text,                -- Pública Federal | Estadual | Municipal | Privada com/sem fins lucrativos
  rede            text,                -- Pública | Privada
  modalidade      text,                -- Presencial | EAD
  grau            text,                -- Bacharelado | Licenciatura | Tecnológico
  area_cine       text,                -- NO_CINE_AREA_GERAL
  rotulo_cine     text,                -- NO_CINE_ROTULO
  co_municipio    text,
  municipio       text,
  qt_ingressante  int      NOT NULL,
  tda numeric, tca numeric, tap numeric, tada numeric, tcan numeric,
  n_desist        numeric  NOT NULL,   -- acumulado até ano_ref
  n_concl         numeric  NOT NULL,   -- acumulado até ano_ref
  n_perm          numeric  NOT NULL,
  n_desist_ano    numeric  NOT NULL,   -- só do ano_ref (TADA)
  PRIMARY KEY (coorte, ano_ref, co_curso)
);

-- -----------------------------------------------------------------------------
-- P3 / B2 · Censo (INEP) graduação em MT. Grão: ano × curso × município de oferta.
-- EAD = uma linha por polo (município do polo, não do aluno). Para contar cursos
-- use COUNT(DISTINCT co_curso); somar alunos entre polos é correto.
-- -----------------------------------------------------------------------------
CREATE TABLE mart.censo_curso (
  ano             int      NOT NULL,   -- NU_ANO_CENSO
  co_curso        text     NOT NULL,
  no_curso        text,
  co_ies          text,
  no_ies          text,
  categoria_adm   text,
  rede            text,
  modalidade      text,
  grau            text,
  area_cine       text,
  rotulo_cine     text,
  co_municipio    text     NOT NULL,
  municipio       text,
  qt_vagas        int,
  qt_ing          int,
  qt_mat          int,
  qt_conc         int,
  qt_desvinculado int,
  qt_transferido  int,
  qt_trancada     int,
  qt_falecido     int,
  qt_ing_fies     int,
  qt_ing_prouni   int,                 -- PROUNI integral + parcial
  qt_mat_fies     int,
  qt_mat_prouni   int,
  PRIMARY KEY (ano, co_curso, co_municipio)
);

-- Financiamento por curso e ano (rede privada), com faixas de participação (B2).
CREATE VIEW mart.financiamento_curso AS
SELECT ano, co_curso, max(no_curso) AS no_curso, max(area_cine) AS area_cine,
       max(modalidade) AS modalidade, max(categoria_adm) AS categoria_adm,
       max(no_ies) AS no_ies,
       sum(qt_ing) AS qt_ing, sum(qt_ing_fies) AS qt_ing_fies, sum(qt_ing_prouni) AS qt_ing_prouni,
       sum(qt_mat) AS qt_mat, sum(qt_mat_fies) AS qt_mat_fies, sum(qt_mat_prouni) AS qt_mat_prouni,
       sum(qt_desvinculado) AS qt_desvinculado, sum(qt_transferido) AS qt_transferido,
       CASE WHEN sum(qt_ing) = 0 THEN NULL
            WHEN sum(qt_ing_fies) = 0 THEN '0%'
            WHEN sum(qt_ing_fies)::numeric / sum(qt_ing) < 0.10 THEN '01–10%'
            WHEN sum(qt_ing_fies)::numeric / sum(qt_ing) < 0.25 THEN '10–25%'
            ELSE '25% ou mais' END AS faixa_fies,
       CASE WHEN sum(qt_ing) = 0 THEN NULL
            WHEN sum(qt_ing_prouni) = 0 THEN '0%'
            WHEN sum(qt_ing_prouni)::numeric / sum(qt_ing) < 0.10 THEN '01–10%'
            WHEN sum(qt_ing_prouni)::numeric / sum(qt_ing) < 0.25 THEN '10–25%'
            ELSE '25% ou mais' END AS faixa_prouni
FROM mart.censo_curso
WHERE rede = 'Privada'
GROUP BY ano, co_curso;

-- -----------------------------------------------------------------------------
-- P4 · CPC × desistência. Grão: ano do CPC × curso.
-- Regra: CPC do ano Y é comparado à coorte Y-3 no 4º ano do curso (ingresso Y-3 →
-- situação em Y). Cursos sem CPC na edição ficam como 'Sem CPC' (NÃO é zero).
-- -----------------------------------------------------------------------------
CREATE TABLE mart.cpc_curso (
  ano_cpc         int      NOT NULL,
  coorte_cpc      int      NOT NULL,   -- ano_cpc - 3 (nome distinto de 'coorte' p/ não colidir com o filtro nativo)
  co_curso        text     NOT NULL,
  no_curso        text,
  area_avaliacao  text,
  area_cine       text,
  no_ies          text,
  categoria_adm   text,
  rede            text,
  modalidade      text,
  municipio       text,
  cpc_faixa       text     NOT NULL,   -- 'CPC 1'..'CPC 5' | 'Sem CPC'
  cpc_continuo    numeric,
  qt_ingressante  int,
  n_desist        numeric,
  tda             numeric,
  PRIMARY KEY (ano_cpc, co_curso)
);

-- -----------------------------------------------------------------------------
-- P5 · Licenciaturas. Grão: curso (coorte de referência fixa).
-- -----------------------------------------------------------------------------
CREATE TABLE mart.licenciatura_curso (
  coorte_ref      int      NOT NULL,
  co_curso        text     NOT NULL,
  no_curso        text,
  area_avaliacao  text     NOT NULL,   -- Área de Avaliação do Enade
  no_ies          text,
  categoria_adm   text,
  rede            text,
  modalidade      text,
  municipio       text,
  qt_ingressante  int,
  n_desist        numeric,
  tda             numeric,
  participantes   int,                 -- concluintes participantes do Enade 2025
  n_padrao        int,                 -- igual ou acima do Padrão 1 de proficiência
  pct_padrao      numeric,             -- 0–100
  conceito_faixa  text,
  PRIMARY KEY (co_curso)
);

-- -----------------------------------------------------------------------------
-- B1 · Desertos. Grão: município (os 142 de MT, vindos do IBGE; zero = sem oferta).
-- -----------------------------------------------------------------------------
CREATE TABLE mart.oferta_municipio (
  co_municipio    text     PRIMARY KEY,
  municipio       text     NOT NULL,
  vagas_pres      int      NOT NULL,   -- QT_VG_TOTAL presencial 2024
  vagas_pres_pub  int      NOT NULL,
  vagas_pres_priv int      NOT NULL,
  pop_18_24       int      NOT NULL,   -- IBGE tabela 9514, Censo 2022
  vagas_por_100   numeric  NOT NULL,
  faixa_oferta    text     NOT NULL    -- '1. Sem oferta' | '2. Até 5' | '3. 5–15' | '4. 15–30' | '5. Mais de 30'
);

-- -----------------------------------------------------------------------------
-- Checagens automáticas da transformação (rubrica: "tem checagens automatizadas").
-- -----------------------------------------------------------------------------
CREATE TABLE mart.qualidade_checks (
  etapa      text NOT NULL,
  checagem   text NOT NULL,
  valor      numeric,
  esperado   text,
  ok         boolean
);
