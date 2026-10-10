<!-- GERADO por: python -m app.knowledge (container chatbot). Não edite à mão: rode de novo depois de mudar o dashboard. -->
# Dicionário de dados do chatbot

Tudo o que o assistente de IA sabe sobre o dashboard. Sai do bundle do Superset (`superset/bundle`) e de `outputs/_indicadores.json`.

## Tabelas do dashboard (schema gold, PostgreSQL)

### gold.b1_desertos_municipio
B1 · Vagas presenciais por 100 jovens de 18 a 24 anos (Censo da Educação Superior × IBGE 2022). Zero = sem oferta.
- populacao: Os 141 municípios de MT
- numerador: Vagas presenciais de graduação ofertadas no município (último Censo carregado)
- denominador: População de 18 a 24 anos (Censo IBGE 2022)
- periodo: Censo da Educação Superior mais recente; população 2022
- agregacao: Soma dos cursos do município
- grao: município
Colunas:
  - co_municipio (TEXT)
  - no_municipio (TEXT) — Município
  - nu_ano_censo (BIGINT)
  - nu_populacao_18_24 (BIGINT)
  - nu_cursos_presenciais (BIGINT)
  - nu_vagas_presenciais (BIGINT)
  - vagas_por_100_jovens (NUMERIC)
  - is_deserto (BOOLEAN)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Vagas por 100 jovens» = 100.0 * SUM(nu_vagas_presenciais) / NULLIF(SUM(nu_populacao_18_24), 0)
  - «Vagas presenciais» = SUM(nu_vagas_presenciais)
  - «Jovens de 18 a 24 anos» = SUM(nu_populacao_18_24)
  - «Municípios» = COUNT(*)
  - «Municípios sem oferta presencial» = SUM(CASE WHEN is_deserto THEN 1 ELSE 0 END)

### gold.b2_financiamento_ano
B2 · Peso de FIES e ProUni na rede privada. Grão: ano × modalidade.
- populacao: Ingressantes e matrículas da rede privada em MT
- numerador: Ingressantes ou matrículas com FIES; com ProUni (integral + parcial)
- denominador: Ingressantes ou matrículas
- periodo: Censo 2021 a 2024
- agregacao: Soma
- grao: ano x modalidade
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - nu_ano_censo (BIGINT) — Ano do Censo
  - modalidade (TEXT)
  - nu_cursos (BIGINT)
  - qt_ingressante (BIGINT)
  - qt_ingressante_fies (BIGINT)
  - qt_ingressante_prouni (BIGINT)
  - qt_matricula (BIGINT)
  - qt_matricula_fies (BIGINT)
  - qt_matricula_prouni (BIGINT)
  - pct_ingressante_fies (NUMERIC)
  - pct_ingressante_prouni (NUMERIC)
  - pct_matricula_fies (NUMERIC)
  - pct_matricula_prouni (NUMERIC)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «FIES (% dos ingressantes)» = 100.0 * SUM(COALESCE(qt_ingressante_fies, 0)) / NULLIF(SUM(qt_ingressante), 0)
  - «ProUni (% dos ingressantes)» = 100.0 * SUM(COALESCE(qt_ingressante_prouni, 0)) / NULLIF(SUM(qt_ingressante), 0)
  - «FIES (% dos matriculados)» = 100.0 * SUM(COALESCE(qt_matricula_fies, 0)) / NULLIF(SUM(qt_matricula), 0)
  - «ProUni (% dos matriculados)» = 100.0 * SUM(COALESCE(qt_matricula_prouni, 0)) / NULLIF(SUM(qt_matricula), 0)
  - «Ingressantes» = SUM(qt_ingressante)
  - «Matrículas» = SUM(qt_matricula)
  - «Cursos» = SUM(nu_cursos)

### gold.b2_financiamento_desistencia
B2 · Desistência no 4º ano por quartil de financiamento (cursos privados com 30+ ingressantes).
- populacao: Cursos privados de MT com 30 ou mais ingressantes na Trajetória
- numerador: Desistentes até o 4º ano
- denominador: Ingressantes
- periodo: Coortes 2015 a 2020; financiamento médio do Censo 2021 a 2024
- agregacao: Soma dos cursos do quartil
- grao: quartil de financiamento
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - quartil_financiamento (BIGINT) — Quartil de financiamento
  - pct_financiado_min (NUMERIC)
  - pct_financiado_max (NUMERIC)
  - nu_cursos (BIGINT)
  - qt_ingressante (BIGINT)
  - qt_desistencia_marco (BIGINT)
  - taxa_desistencia_marco (NUMERIC)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Saíram do curso em 4 anos (%)» = SUM(taxa_desistencia_marco * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_desistencia_marco IS NOT NULL THEN qt_ingressante END), 0)
  - «Ingressantes» = SUM(qt_ingressante)
  - «Cursos» = SUM(nu_cursos)
  - «% financiado (mín.)» = MIN(pct_financiado_min)
  - «% financiado (máx.)» = MAX(pct_financiado_max)

### gold.controle_atualizacao
Última carga de cada fonte.
Colunas:
  - fonte (TEXT)
  - ultimo_status (TEXT)
  - ultima_carga_sucesso_local (TIMESTAMP)
  - ultima_carga_sucesso_utc (TIMESTAMP)
  - linhas_ultima_execucao (BIGINT)
  - linhas_rejeitadas_ultima_execucao (BIGINT)
  - ultima_transformacao_local (TIMESTAMP)
  - fuso_horario (TEXT)

### gold.p1_trajetoria_coorte
P1 · Indicadores de Trajetória (INEP). Grão: modalidade × coorte × ano de referência. Taxas já em %, ponderadas pelos ingressantes ao reagregar.
- populacao: Ingressantes de cursos de graduação de MT na coorte (Indicadores de Trajetória)
- numerador: Desistentes, concluintes e permanentes acumulados até o ano de referência
- denominador: Ingressantes da coorte
- periodo: Coortes 2015 a 2020, acompanhadas até 2024
- agregacao: Soma de todos os cursos da modalidade; nunca média de taxas
- grao: modalidade x coorte x ano de referência
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - modalidade (TEXT)
  - nu_ano_ingresso (BIGINT) — Coorte (ano de ingresso)
  - nu_ano_referencia (BIGINT) — Ano de referência
  - nu_ano_curso (BIGINT) — Ano do curso
  - nu_cursos (BIGINT)
  - qt_ingressante (BIGINT)
  - qt_permanencia (BIGINT)
  - qt_concluinte_ano (BIGINT)
  - qt_desistencia_ano (BIGINT)
  - qt_concluinte_acum (BIGINT)
  - qt_desistencia_acum (BIGINT)
  - qt_falecido_acum (BIGINT)
  - taxa_desistencia_acum (NUMERIC)
  - taxa_conclusao_acum (NUMERIC)
  - taxa_permanencia (NUMERIC)
  - taxa_desistencia_ano (NUMERIC)
  - taxa_desistencia_sobre_ativos (NUMERIC)
  - is_ano_maior_perda (BOOLEAN)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Concluíram» = SUM(taxa_conclusao_acum * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_conclusao_acum IS NOT NULL THEN qt_ingressante END), 0)
  - «Saíram do curso» = SUM(taxa_desistencia_acum * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_desistencia_acum IS NOT NULL THEN qt_ingressante END), 0)
  - «Em curso» = SUM(taxa_permanencia * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_permanencia IS NOT NULL THEN qt_ingressante END), 0)
  - «Saídas no ano» = SUM(taxa_desistencia_ano * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_desistencia_ano IS NOT NULL THEN qt_ingressante END), 0)
  - «Ingressantes» = SUM(qt_ingressante)
  - «Cursos» = MAX(nu_cursos)

### gold.p2_desistencia_area
P2 · Desistência por área CINE, coorte e ano do curso. Grão: área × modalidade × coorte × ano do curso.
- populacao: Ingressantes de MT por área geral CINE
- numerador: Desistentes acumulados até o ano do curso
- denominador: Ingressantes
- periodo: Coortes 2015 a 2020
- agregacao: Soma dos cursos da área
- grao: área x modalidade x coorte x ano do curso
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - no_cine_area_geral (TEXT) — Área (CINE)
  - modalidade (TEXT)
  - nu_ano_ingresso (BIGINT) — Coorte (ano de ingresso)
  - nu_ano_curso (BIGINT) — Ano do curso
  - nu_cursos (BIGINT)
  - qt_ingressante (BIGINT)
  - qt_desistencia_acum (BIGINT)
  - taxa_desistencia_acum (NUMERIC)
  - taxa_conclusao_acum (NUMERIC)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Saíram do curso» = SUM(taxa_desistencia_acum * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_desistencia_acum IS NOT NULL THEN qt_ingressante END), 0)
  - «Concluíram» = SUM(taxa_conclusao_acum * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_conclusao_acum IS NOT NULL THEN qt_ingressante END), 0)
  - «Ingressantes» = SUM(qt_ingressante)
  - «Cursos» = SUM(nu_cursos)

### gold.p2_desistencia_curso
P2 · Desistência por curso e coorte no mesmo ano do curso (4º, padrão do dbt). Grão: curso × coorte.
- populacao: Ingressantes de cada curso de MT por coorte
- numerador: Desistentes acumulados até o ano do curso de comparação (padrão 4º ano)
- denominador: Ingressantes da coorte no curso
- periodo: Coortes 2015 a 2020; comparação sempre no mesmo ano do curso
- agregacao: Nenhuma; um curso por linha. Ranking só com 30 ou mais ingressantes
- grao: curso x coorte
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - co_curso (TEXT)
  - nu_ano_ingresso (BIGINT) — Coorte (ano de ingresso)
  - no_curso (TEXT) — Nome do curso
  - no_ies (TEXT) — Instituição
  - rede (TEXT)
  - modalidade (TEXT)
  - grau_academico (TEXT)
  - no_cine_area_geral (TEXT) — Área (CINE)
  - no_cine_rotulo (TEXT) — Curso (rótulo CINE)
  - nu_ano_curso_marco (BIGINT) — Ano do curso da comparação
  - qt_ingressante (BIGINT)
  - qt_desistencia_marco (BIGINT)
  - taxa_desistencia_marco (NUMERIC)
  - taxa_conclusao_marco (NUMERIC)
  - nu_ultimo_ano_observado (BIGINT)
  - taxa_desistencia_final (NUMERIC)
  - taxa_conclusao_final (NUMERIC)
  - is_elegivel_ranking (BOOLEAN)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Saíram do curso (4º ano)» = SUM(taxa_desistencia_marco * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_desistencia_marco IS NOT NULL THEN qt_ingressante END), 0)
  - «Concluíram (4º ano)» = SUM(taxa_conclusao_marco * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_conclusao_marco IS NOT NULL THEN qt_ingressante END), 0)
  - «Ingressantes» = SUM(qt_ingressante)
  - «Cursos» = COUNT(DISTINCT co_curso)

### gold.p3_rede_modalidade_ano
P3 · Censo da Educação Superior 2021–2024. Grão: ano × rede × modalidade.
- populacao: Vínculos de graduação em cursos ofertados em MT no ano
- numerador: Vínculos desvinculados no ano (QT_SIT_DESVINCULADO)
- denominador: Matrículas + trancadas + desvinculados + transferidos + falecidos
- periodo: Censo 2021 a 2024
- agregacao: Soma de municípios e cursos
- grao: ano x rede x modalidade
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - nu_ano_censo (BIGINT) — Ano do Censo
  - rede (TEXT)
  - modalidade (TEXT)
  - nu_cursos (BIGINT)
  - nu_vagas (BIGINT)
  - qt_ingressante (BIGINT)
  - qt_matricula (BIGINT)
  - qt_concluinte (BIGINT)
  - qt_trancada (BIGINT)
  - qt_desvinculado (BIGINT)
  - qt_transferido (BIGINT)
  - qt_vinculo (BIGINT)
  - taxa_evasao_anual (NUMERIC)
  - taxa_trancamento (NUMERIC)
  - variacao_evasao_pp (NUMERIC)
  - variacao_matricula_pct (NUMERIC)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Evasão anual (%)» = 100.0 * SUM(qt_desvinculado) / NULLIF(SUM(qt_matricula + qt_desvinculado + qt_transferido), 0)
  - «Evasão anual · base Gold (%)» = 100.0 * SUM(qt_desvinculado) / NULLIF(SUM(qt_vinculo), 0)
  - «Matrículas» = SUM(qt_matricula)
  - «Desvinculados» = SUM(qt_desvinculado)
  - «Base da evasão (guia)» = SUM(qt_matricula + qt_desvinculado + qt_transferido)
  - «Variação da evasão (p.p.)» = MAX(variacao_evasao_pp)
  - «Variação das matrículas (%)» = MAX(variacao_matricula_pct)

### gold.p4_fatores
P4 · Correlação de Pearson de cada componente do CPC com a desistência no 4º ano (um curso, um ponto).
- populacao: Cursos com CPC e 30 ou mais ingressantes
- numerador: Correlação de Pearson entre fator e taxa de desistência
- denominador: Não se aplica
- periodo: Coortes 2015 a 2020; CPC 2021 a 2023
- agregacao: Um curso, um ponto; não ponderado
- grao: fator
Colunas:
  - fator (TEXT)
  - correlacao_pearson (NUMERIC)
  - nu_cursos (BIGINT)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Correlação (Pearson)» = MAX(correlacao_pearson)
  - «Cursos» = MAX(nu_cursos)

### gold.p4_qualidade_curso
P4 · CPC e desistência no 4º ano por curso (coortes somadas).
- populacao: Cursos de MT com coorte observada até o ano do curso de comparação
- numerador: Desistentes acumulados até o 4º ano, coortes somadas
- denominador: Ingressantes das mesmas coortes
- periodo: Coortes 2015 a 2020; CPC mais recente entre 2021 e 2023
- agregacao: Soma das coortes do curso
- grao: curso
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - co_curso (TEXT)
  - no_curso (TEXT) — Nome do curso
  - no_ies (TEXT) — Instituição
  - rede (TEXT)
  - modalidade (TEXT)
  - grau_academico (TEXT)
  - no_cine_area_geral (TEXT) — Área (CINE)
  - nu_coortes (BIGINT)
  - nu_ano_curso_marco (BIGINT)
  - qt_ingressante (BIGINT)
  - qt_desistencia_marco (BIGINT)
  - taxa_desistencia_marco (NUMERIC)
  - nu_edicao_cpc (BIGINT)
  - cpc_faixa (TEXT)
  - cpc_continuo (NUMERIC)
  - enade_continuo (NUMERIC)
  - idd_padronizado (NUMERIC)
  - doutores_padronizado (NUMERIC)
  - regime_trabalho_padronizado (NUMERIC)
  - infraestrutura_padronizado (NUMERIC)
  - didatico_pedagogica_padronizado (NUMERIC)
  - tem_cpc (BOOLEAN)
  - is_elegivel_ranking (BOOLEAN)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Saíram do curso em 4 anos (%)» = SUM(taxa_desistencia_marco * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_desistencia_marco IS NOT NULL THEN qt_ingressante END), 0)
  - «Ingressantes» = SUM(qt_ingressante)
  - «Cursos» = COUNT(DISTINCT co_curso)
  - «CPC médio» = AVG(cpc_continuo)

### gold.p4_qualidade_faixa
P4 · Desistência no 4º ano por faixa de CPC e rede.
- populacao: Cursos de P4 agrupados por faixa de CPC
- numerador: Desistentes até o 4º ano
- denominador: Ingressantes
- periodo: Coortes 2015 a 2020; CPC 2021 a 2023
- agregacao: Soma dos cursos da faixa
- grao: faixa CPC x rede
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - cpc_faixa (TEXT)
  - rede (TEXT)
  - nu_cursos (BIGINT)
  - qt_ingressante (BIGINT)
  - qt_desistencia_marco (BIGINT)
  - taxa_desistencia_marco (NUMERIC)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Saíram do curso em 4 anos (%)» = SUM(taxa_desistencia_marco * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_desistencia_marco IS NOT NULL THEN qt_ingressante END), 0)
  - «Ingressantes» = SUM(qt_ingressante)
  - «Cursos» = SUM(nu_cursos)

### gold.p5_funil_licenciaturas
P5 · De cada 100 que entram: quantos desistem, concluem e concluem proficientes (a última etapa é estimativa).
- populacao: Licenciaturas de MT
- numerador: Desistentes e concluintes no último ano observado; proficientes ponderados por participantes
- denominador: Ingressantes; participantes do Enade
- periodo: Coortes 2015 a 2020 até 2024; Enade 2025
- agregacao: Soma; proficiência ponderada pelo número de participantes
- grao: rede (com linha Total)
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - rede (TEXT)
  - nu_cursos (BIGINT)
  - qt_ingressante (BIGINT)
  - de_100_desistem (NUMERIC)
  - de_100_concluem (NUMERIC)
  - nu_cursos_enade (BIGINT)
  - qt_participante_enade (BIGINT)
  - pct_proficiente (NUMERIC)
  - de_100_concluem_proficientes (NUMERIC)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Desistem (de cada 100)» = MAX(de_100_desistem)
  - «Concluem (de cada 100)» = MAX(de_100_concluem)
  - «Concluem proficientes (de cada 100, estimativa)» = MAX(de_100_concluem_proficientes)
  - «Ingressantes» = SUM(qt_ingressante)
  - «No padrão de proficiência (%)» = MAX(pct_proficiente)

### gold.p5_licenciaturas_curso
P5 · Licenciaturas de MT: desistência (Trajetória) e proficiência no Enade 2025, por curso.
- populacao: Cursos de licenciatura de MT na Trajetória
- numerador: Desistentes e concluintes; concluintes proficientes no Enade
- denominador: Ingressantes; participantes do Enade
- periodo: Coortes 2015 a 2020; Enade 2025
- agregacao: Soma das coortes do curso
- grao: curso
- celulas_pequenas: Linhas com base abaixo de 10 alunos não são publicadas; contagens qt_* entre 1 e 9 saem vazias. Taxas são calculadas antes da máscara, sempre como soma do numerador sobre soma do denominador.
Colunas:
  - co_curso (TEXT)
  - no_curso (TEXT) — Licenciatura
  - no_ies (TEXT) — Instituição
  - rede (TEXT)
  - modalidade (TEXT)
  - no_cine_area_geral (TEXT) — Área (CINE)
  - nu_coortes (BIGINT)
  - qt_ingressante (BIGINT)
  - taxa_desistencia_marco (NUMERIC)
  - taxa_desistencia_final (NUMERIC)
  - taxa_conclusao_final (NUMERIC)
  - area_enade (TEXT) — Área de avaliação (Enade)
  - qt_participante_enade (BIGINT)
  - pct_proficiente (NUMERIC)
  - conceito_enade_faixa (TEXT)
  - tem_enade (BOOLEAN)
Métricas do dashboard (use estas fórmulas ao reagregar):
  - «Saíram do curso (%)» = SUM(taxa_desistencia_final * qt_ingressante) / NULLIF(SUM(CASE WHEN taxa_desistencia_final IS NOT NULL THEN qt_ingressante END), 0)
  - «No padrão de proficiência ou acima (%)» = SUM(pct_proficiente * qt_participante_enade) / NULLIF(SUM(CASE WHEN pct_proficiente IS NOT NULL THEN qt_participante_enade END), 0)
  - «Ingressantes» = SUM(qt_ingressante)
  - «Concluintes participantes» = SUM(qt_participante_enade)
  - «Cursos» = COUNT(DISTINCT co_curso)

## Gráficos do dashboard (por aba)

- Atualização · última carga de cada fonte: Quando cada fonte foi carregada e quantas linhas foram lidas/rejeitadas (tabela controle_atualizacao da Gold).
- B1 · Maiores desertos (sem oferta, por população jovem): Municípios sem nenhuma vaga presencial, ordenados pela população de 18 a 24 anos (onde há mais jovens sem oferta local).
- B1 · Municípios: Todos os municípios de MT vêm do IBGE; quem não tem curso entra com zero vagas.
- B1 · Municípios com maior oferta (vagas por 100 jovens): Os 15 municípios com mais vagas presenciais por 100 jovens de 18 a 24 anos.
- B1 · Municípios sem oferta presencial: Contagem de municípios com zero vagas presenciais (is_deserto).
- B1 · Quantos municípios em cada faixa de oferta: Distribuição dos municípios por faixa de vagas por 100 jovens. "Sem oferta" = zero vagas presenciais.
- B1 · Vagas por 100 jovens (MT): Soma das vagas ÷ soma da população dos municípios do recorte. Fonte: INEP, Censo da Educação Superior; IBGE/SIDRA tabela 9514 (Censo 2022).
- B1 · Vagas presenciais: Soma de vagas presenciais dos cursos de graduação.
- B2 · Bases de cálculo por ano: Cursos, ingressantes e taxas por ano e modalidade na rede privada. Fonte: INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).
- B2 · Bases de cálculo por quartil: Faixa de % financiado de cada quartil, número de cursos, ingressantes e taxa.
- B2 · Desistência no 4º ano por quartil de financiamento: Cursos privados com 30+ ingressantes divididos em quartis pela participação média de financiamento; desistência ponderada em cada quartil. Associação, não causa. Fonte: Trajetória + Censo. Camada gold.
- B2 · Peso do FIES e do ProUni entre os ingressantes: Participação de FIES e de ProUni (integral + parcial), separadamente, entre os ingressantes da rede privada. Os programas não são somados entre si. Fonte: INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).
- B2 · Peso do FIES e do ProUni entre os matriculados: Mesma leitura, agora sobre os matriculados. Fonte: INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).
- P1 · Bases de cálculo por ano: Mesmos números do gráfico, em tabela, com a base (ingressantes). Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P1 · Concluíram (%): Taxa de conclusão acumulada (TCA). Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P1 · Em curso (%): Taxa de permanência (TAP). Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P1 · Em que ano do curso a perda é maior?: Desistentes de cada ano sobre os ingressantes da coorte. A barra mais alta é o ano de maior perda.  Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P1 · Saíram do curso (%): Taxa de desistência acumulada (TDA). "Saíram do curso" não significa necessariamente abandono da graduação. Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P1 · Situação da coorte ao fim de cada ano: Cada coluna soma 100%: concluíram + saíram do curso + em curso, acumulado até o ano. Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P1 · Total de ingressantes: Soma de QT_INGRESSANTE da coorte nos cursos presenciais de MT. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P2 · Área × coorte no mesmo ano do curso: Compara COORTES diferentes no MESMO ano do curso (filtro "Ano do curso"), nunca na mesma data. Cada célula é a desistência acumulada ponderada da área naquela coorte. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P2 · Bases de cálculo por curso (rótulo): Taxa (ponderada), base de ingressantes e número de cursos por rótulo, no 4º ano do curso.  Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P2 · Curso (rótulo CINE) × coorte no 4º ano do curso: Desistência acumulada até o 4º ano do curso, por rótulo CINE e coorte. Só rótulos com 30+ ingressantes. Compare colunas (coortes) na mesma linha. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P2 · Cursos com maior desistência no 4º ano: Cursos (rótulo CINE) ordenados pela desistência acumulada até o 4º ano do curso, na coorte escolhida. Só entram rótulos com 30 ou mais ingressantes. Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P2 · Cursos com menor desistência no 4º ano: Cursos (rótulo CINE) ordenados pela desistência acumulada até o 4º ano do curso, na coorte escolhida. Só entram rótulos com 30 ou mais ingressantes. Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P2 · Desistência por área geral (CINE): Áreas gerais CINE ordenadas pela desistência acumulada ponderada, no ano do curso e na coorte escolhidos.  Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P3 · Bases da evasão anual: Numerador (desvinculados) e denominador (matriculados + desvinculados + transferidos) da evasão anual, e a taxa com a base da Gold (que inclui trancadas e falecidos). Fonte: INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).
- P3 · Distribuição das matrículas: Participação de cada rede × modalidade no total de matrículas do ano (colunas somam 100%). Fonte: INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).
- P3 · Evasão anual por rede e modalidade: Evasão anual (proxy do Censo) = desvinculados ÷ (matriculados + desvinculados + transferidos), no ano. Mede a perda DAQUELE ano, não a da turma inteira. A Gold calcula com outro denominador (inclui trancadas e falecidos): veja "base Gold" na tabela de bases. Fonte: INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).
- P3 · Variação da evasão (p.p. sobre o ano anterior): Diferença em pontos percentuais da evasão para o ano anterior (calculada na Gold). Destaca ano atípico: um valor que dispara e volta ao normal pede investigação antes de virar conclusão. Fonte: INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).
- P3 · Variação das matrículas (% sobre o ano anterior): Variação percentual das matrículas sobre o ano anterior (Gold). Saltos (ex.: 2023) pedem explicação antes da conclusão. Fonte: INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).
- P4 · CPC contínuo × desistência (um ponto por curso): Cada bolha é um curso (tamanho = ingressantes), cor = rede. Só cursos com CPC e 30+ ingressantes. Associação, não causa. Fonte: INEP, CPC 2021–2023 + Trajetória.
- P4 · Cobertura e bases por faixa: Quantos cursos e ingressantes há em cada faixa, incluindo "Sem CPC" (cobertura). Taxa ponderada pelos ingressantes.
- P4 · Controle: faixa do CPC × modalidade: Mesma comparação separada por modalidade (presencial × EAD).
- P4 · Controle: faixa do CPC × rede: Mesma comparação separada por rede: se a relação some dentro de cada rede, a rede explica parte do efeito aparente.
- P4 · Desistência por faixa do CPC: Desistência acumulada até o 4º ano por faixa do CPC, ponderada pelos ingressantes. "Sem CPC" (SC ou sem edição) não é nota zero. Associação observada, não causa. Fonte: INEP, CPC 2021–2023 + Trajetória. Camada gold.
- P4 · O que mais explica a desistência (correlação): Correlação de Pearson (um curso, um ponto, não ponderada) de cada componente do CPC com a taxa de desistência no 4º ano. Valores positivos: mais do fator, mais desistência. Correlação não é causa.
- P5 · Bases de cálculo por licenciatura: Bases de cada medida. Desistência: Trajetória. Proficiência: Enade 2025 (vazia onde não há participantes suficientes).
- P5 · Concluem (de cada 100): Concluintes no último ano observado sobre ingressantes. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P5 · Concluem proficientes (de cada 100): Concluem × % de concluintes no padrão de proficiência (Enade 2025). Estimativa: os concluintes do Enade não são a mesma turma. Fonte: INEP, Conceito Enade 2025 · Licenciaturas.
- P5 · Desistem (de cada 100): Desistentes no último ano observado sobre ingressantes. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P5 · Desistência por licenciatura: As 15 licenciaturas com maior desistência até o último ano observado, ponderada pelos ingressantes (somando instituições). Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P5 · Funil por rede (de cada 100 que entram): Para cada rede e para o total: quantos de cada 100 ingressantes desistem, concluem e concluem proficientes (estimativa). Fonte: Trajetória + Enade Licenciaturas 2025. Camada gold.
- P5 · Ingressantes em licenciaturas: Soma de QT_INGRESSANTE das licenciaturas de MT. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- P5 · Proficiência por área (Enade 2025): As 15 áreas com menor % de concluintes participantes no padrão de proficiência ou acima (Enade, ponderado por participantes). Células com menos de 10 participantes não são publicadas. Fonte: INEP, Conceito Enade 2025 · Licenciaturas.
- P5 · Quem forma pouco e com baixa proficiência: Cada bolha é um curso de licenciatura, colorido pela licenciatura. Canto superior-esquerdo = muita desistência e baixa proficiência. Tamanho = concluintes participantes (formam pouco = bolha pequena). Bases distintas.
- Visão geral · Concluíram (%): Taxa de conclusão acumulada (TCA). Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- Visão geral · Cursos com maior desistência no 4º ano: Cursos (rótulo CINE) ordenados pela desistência acumulada até o 4º ano do curso, na coorte escolhida. Só entram rótulos com 30 ou mais ingressantes. Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- Visão geral · Desistência por faixa do CPC: Desistência acumulada até o 4º ano por faixa do CPC, ponderada pelos ingressantes. "Sem CPC" (SC ou sem edição) não é nota zero. Associação observada, não causa. Fonte: INEP, CPC 2021–2023 + Trajetória. Camada gold.
- Visão geral · Em curso (%): Taxa de permanência (TAP). Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- Visão geral · Evasão anual por rede e modalidade: Evasão anual (proxy do Censo) = desvinculados ÷ (matriculados + desvinculados + transferidos), no ano. Mede a perda DAQUELE ano, não a da turma inteira. A Gold calcula com outro denominador (inclui trancadas e falecidos): veja "base Gold" na tabela de bases. Fonte: INEP, Censo da Educação Superior (cursos), 2021–2024. Camada gold do warehouse (dbt).
- Visão geral · Saíram do curso (%): Taxa de desistência acumulada (TDA). "Saíram do curso" não significa necessariamente abandono da graduação. Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- Visão geral · Situação da coorte ao fim de cada ano: Cada coluna soma 100%: concluíram + saíram do curso + em curso, acumulado até o ano. Taxas já vêm calculadas na Gold (soma do numerador sobre soma do denominador) e, ao reagregar aqui, são ponderadas pelo número de ingressantes (nunca média simples). Grupos com menos de 10 alunos não são publicados. Filtro fixo: cursos presenciais. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).
- Visão geral · Total de ingressantes: Soma de QT_INGRESSANTE da coorte nos cursos presenciais de MT. Fonte: INEP, Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024). Camada gold do warehouse (dbt).

## Abas do dashboard
- Visão geral
- P1 · Trajetória
- P2 · Cursos e áreas
- P3 · Rede e modalidade
- P4 · CPC e desistência
- P5 · Licenciaturas
- B1 · Desertos de ensino superior
- B2 · Financiamento
- Fontes e metodologia

## Filtros do dashboard
- Coorte (ano de ingresso)
- Modalidade (trajetória)
- Ano do curso (áreas)
- Rede
- Modalidade
- Grau acadêmico
- Área (CINE)
- Curso (rótulo CINE)
- Instituição
- Faixa do CPC
- CPC contínuo (0–5)
- Licenciatura
- Área de avaliação (Enade)
- Ano do Censo
- Quartil de financiamento
- Município
- Faixa de oferta
- Vagas por 100 jovens
- Jovens de 18 a 24 anos