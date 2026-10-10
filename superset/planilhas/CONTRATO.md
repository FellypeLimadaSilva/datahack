# Contrato das planilhas (Plano B)

> Gerado por `superset/build_bundle.js`; não edite à mão. Uma tabela = um arquivo (ou uma aba) com o nome abaixo.
> Regras de nomes, formatos aceitos e como carregar: `superset/planilhas/LEIA-ME.md`.

## p1_trajetoria_coorte

P1 · Indicadores de Trajetória (INEP). Grão: modalidade × coorte × ano de referência. Taxas já em %, ponderadas pelos ingressantes ao reagregar. Em "Exibir em: Número", as métricas viram contagens de estudantes.

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `modalidade` | texto |  |
| `nu_ano_ingresso` | inteiro | Coorte (ano de ingresso) |
| `nu_ano_referencia` | inteiro | Ano de referência |
| `nu_ano_curso` | inteiro | Ano do curso |
| `nu_cursos` | inteiro |  |
| `qt_ingressante` | inteiro |  |
| `qt_permanencia` | inteiro |  |
| `qt_concluinte_ano` | inteiro |  |
| `qt_desistencia_ano` | inteiro |  |
| `qt_concluinte_acum` | inteiro |  |
| `qt_desistencia_acum` | inteiro |  |
| `qt_falecido_acum` | inteiro |  |
| `taxa_desistencia_acum` | número |  |
| `taxa_conclusao_acum` | número |  |
| `taxa_permanencia` | número |  |
| `taxa_desistencia_ano` | número |  |
| `taxa_desistencia_sobre_ativos` | número |  |
| `is_ano_maior_perda` | verdadeiro/falso |  |

## p2_desistencia_curso

P2 · Desistência por curso e coorte no mesmo ano do curso (4º, padrão do dbt). Grão: curso × coorte.

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `co_curso` | texto |  |
| `nu_ano_ingresso` | inteiro | Coorte (ano de ingresso) |
| `no_curso` | texto | Nome do curso |
| `no_ies` | texto | Instituição |
| `rede` | texto |  |
| `modalidade` | texto |  |
| `grau_academico` | texto |  |
| `no_cine_area_geral` | texto | Área (CINE) |
| `no_cine_rotulo` | texto | Curso (rótulo CINE) |
| `nu_ano_curso_marco` | inteiro | Ano do curso da comparação |
| `qt_ingressante` | inteiro |  |
| `qt_desistencia_marco` | inteiro |  |
| `taxa_desistencia_marco` | número |  |
| `taxa_conclusao_marco` | número |  |
| `nu_ultimo_ano_observado` | inteiro |  |
| `taxa_desistencia_final` | número |  |
| `taxa_conclusao_final` | número |  |
| `is_elegivel_ranking` | verdadeiro/falso |  |

## p2_desistencia_area

P2 · Desistência por área CINE, coorte e ano do curso. Grão: área × modalidade × coorte × ano do curso.

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `no_cine_area_geral` | texto | Área (CINE) |
| `modalidade` | texto |  |
| `nu_ano_ingresso` | inteiro | Coorte (ano de ingresso) |
| `nu_ano_curso` | inteiro | Ano do curso |
| `nu_cursos` | inteiro |  |
| `qt_ingressante` | inteiro |  |
| `qt_desistencia_acum` | inteiro |  |
| `taxa_desistencia_acum` | número |  |
| `taxa_conclusao_acum` | número |  |

## p3_rede_modalidade_ano

P3 · Censo da Educação Superior 2021–2024. Grão: ano × rede × modalidade. As variações e a participação nas matrículas são calculadas aqui (janelas) para o modo "Número".

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `nu_ano_censo` | inteiro | Ano do Censo |
| `rede` | texto |  |
| `modalidade` | texto |  |
| `nu_cursos` | inteiro |  |
| `nu_vagas` | inteiro |  |
| `qt_ingressante` | inteiro |  |
| `qt_matricula` | inteiro |  |
| `qt_concluinte` | inteiro |  |
| `qt_trancada` | inteiro |  |
| `qt_desvinculado` | inteiro |  |
| `qt_transferido` | inteiro |  |
| `qt_vinculo` | inteiro |  |
| `taxa_evasao_anual` | número |  |
| `taxa_trancamento` | número |  |
| `variacao_evasao_pp` | número |  |
| `variacao_matricula_pct` | número |  |

## p4_qualidade_curso

P4 · CPC e desistência no 4º ano por curso (coortes somadas).

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `co_curso` | texto |  |
| `no_curso` | texto | Nome do curso |
| `no_ies` | texto | Instituição |
| `rede` | texto |  |
| `modalidade` | texto |  |
| `grau_academico` | texto |  |
| `no_cine_area_geral` | texto | Área (CINE) |
| `nu_coortes` | inteiro |  |
| `nu_ano_curso_marco` | inteiro |  |
| `qt_ingressante` | inteiro |  |
| `qt_desistencia_marco` | inteiro |  |
| `taxa_desistencia_marco` | número |  |
| `nu_edicao_cpc` | inteiro |  |
| `cpc_faixa` | texto |  |
| `cpc_continuo` | número |  |
| `enade_continuo` | número |  |
| `idd_padronizado` | número |  |
| `doutores_padronizado` | número |  |
| `regime_trabalho_padronizado` | número |  |
| `infraestrutura_padronizado` | número |  |
| `didatico_pedagogica_padronizado` | número |  |
| `tem_cpc` | verdadeiro/falso |  |
| `is_elegivel_ranking` | verdadeiro/falso |  |

## p4_qualidade_faixa

P4 · Desistência no 4º ano por faixa de CPC e rede.

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `cpc_faixa` | texto |  |
| `rede` | texto |  |
| `nu_cursos` | inteiro |  |
| `qt_ingressante` | inteiro |  |
| `qt_desistencia_marco` | inteiro |  |
| `taxa_desistencia_marco` | número |  |

## p4_fatores

P4 · Correlação de Pearson de cada componente do CPC com a desistência no 4º ano (um curso, um ponto).

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `fator` | texto |  |
| `correlacao_pearson` | número |  |
| `nu_cursos` | inteiro |  |

## p5_licenciaturas_curso

P5 · Licenciaturas de MT: desistência (Trajetória) e proficiência no Enade 2025, por curso. Em "Número", desistentes e proficientes são estimados por taxa × base.

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `co_curso` | texto |  |
| `no_curso` | texto | Licenciatura |
| `no_ies` | texto | Instituição |
| `rede` | texto |  |
| `modalidade` | texto |  |
| `no_cine_area_geral` | texto | Área (CINE) |
| `nu_coortes` | inteiro |  |
| `qt_ingressante` | inteiro |  |
| `taxa_desistencia_marco` | número |  |
| `taxa_desistencia_final` | número |  |
| `taxa_conclusao_final` | número |  |
| `area_enade` | texto | Área de avaliação (Enade) |
| `qt_participante_enade` | inteiro |  |
| `pct_proficiente` | número |  |
| `conceito_enade_faixa` | texto |  |
| `tem_enade` | verdadeiro/falso |  |

## p5_funil_licenciaturas

P5 · De cada 100 que entram: quantos desistem, concluem e concluem proficientes (a última etapa é estimativa). Em "Número": ingressantes × taxa.

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `rede` | texto |  |
| `nu_cursos` | inteiro |  |
| `qt_ingressante` | inteiro |  |
| `de_100_desistem` | número |  |
| `de_100_concluem` | número |  |
| `nu_cursos_enade` | inteiro |  |
| `qt_participante_enade` | inteiro |  |
| `pct_proficiente` | número |  |
| `de_100_concluem_proficientes` | número |  |

## b1_desertos_municipio

B1 · Vagas presenciais por 100 jovens de 18 a 24 anos (Censo da Educação Superior × IBGE 2022). Zero = sem oferta. Em "Número", o gráfico de oferta mostra as vagas.

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `co_municipio` | texto |  |
| `no_municipio` | texto | Município |
| `nu_ano_censo` | inteiro |  |
| `nu_populacao_18_24` | inteiro |  |
| `nu_cursos_presenciais` | inteiro |  |
| `nu_vagas_presenciais` | inteiro |  |
| `vagas_por_100_jovens` | número |  |
| `is_deserto` | verdadeiro/falso |  |

## b2_financiamento_ano

B2 · Peso de FIES e ProUni na rede privada. Grão: ano × modalidade. Em "Número": estudantes com FIES ou ProUni.

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `nu_ano_censo` | inteiro | Ano do Censo |
| `modalidade` | texto |  |
| `nu_cursos` | inteiro |  |
| `qt_ingressante` | inteiro |  |
| `qt_ingressante_fies` | inteiro |  |
| `qt_ingressante_prouni` | inteiro |  |
| `qt_matricula` | inteiro |  |
| `qt_matricula_fies` | inteiro |  |
| `qt_matricula_prouni` | inteiro |  |
| `pct_ingressante_fies` | número |  |
| `pct_ingressante_prouni` | número |  |
| `pct_matricula_fies` | número |  |
| `pct_matricula_prouni` | número |  |

## b2_financiamento_desistencia

B2 · Desistência no 4º ano por quartil de financiamento (cursos privados com 30+ ingressantes).

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `quartil_financiamento` | inteiro | Quartil de financiamento |
| `pct_financiado_min` | número |  |
| `pct_financiado_max` | número |  |
| `nu_cursos` | inteiro |  |
| `qt_ingressante` | inteiro |  |
| `qt_desistencia_marco` | inteiro |  |
| `taxa_desistencia_marco` | número |  |

## controle_atualizacao

Última carga de cada fonte.

| Coluna | Tipo | Rótulo no dashboard |
|---|---|---|
| `fonte` | texto |  |
| `ultimo_status` | texto |  |
| `ultima_carga_sucesso_local` | data e hora |  |
| `ultima_carga_sucesso_utc` | data e hora |  |
| `linhas_ultima_execucao` | inteiro |  |
| `linhas_rejeitadas_ultima_execucao` | inteiro |  |
| `ultima_transformacao_local` | data e hora |  |
| `fuso_horario` | texto |  |
