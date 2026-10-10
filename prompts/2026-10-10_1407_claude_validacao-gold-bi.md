# Consulta à IA: auditoria da Gold, integração do BI e documentação final

| Campo | Valor |
|---|---|
| Ferramenta | Claude (claude.ai, modo agente com acesso ao repositório, ao terminal e ao GitHub) |
| Quem usou | Fellype Lima da Silva |
| Fase | Fase 3 (Entrega final) |
| Período | 2026-10-10, 14:07 a 16:15 (America/Cuiaba) |
| Objetivo | Auditar os gráficos contra a Gold, corrigir inconsistências, integrar o BI ao DW com menor privilégio e atualizar a documentação |

Registro das consultas que resultaram em decisão ou mudança no projeto, com o pedido em linguagem
técnica, a resposta da IA, a validação da equipe e o commit.

## 1. Repositório e CI

**C1. Proteção da branch principal**
- Pedido: proteger a `main` sem bloquear o fluxo da equipe no dia do evento.
- Resposta: ruleset com bloqueio de exclusão e de force push, sem exigir pull request.
- Validação: ruleset ativo; push normal segue funcionando.

**C2. Falha recorrente no job do laboratório do CI**
- Pedido: identificar a causa do status vermelho nos commits.
- Resposta: análise dos jobs do GitHub Actions; o `dbt debug` falhava porque a imagem CLI não tem `git`. Trocado por `dbt debug --connection`, que valida só a conexão.
- Validação: job do laboratório verde no CI seguinte. Commit `cd6a922`.

## 2. Auditoria da Gold e do dashboard

**C3. Auditoria de cada indicador contra a Gold**
- Pedido: revisar os blocos do dashboard e corrigir na Gold o que estivesse inconsistente.
- Resposta, erros encontrados e corrigidos:

| Onde | Problema | Correção |
|---|---|---|
| Silver e B2 | `ProUni integral + parcial` resultava nulo quando um dos campos vinha vazio, e o curso saía da soma | Campo vazio conta como zero |
| P1 | Com "Todos" no filtro, modalidades e coortes eram desenhadas numa linha só | Modalidade e coorte exigem um valor |
| P5 | "Desistem" aparecia como etapa do funil | Funil: entram → concluem → concluem proficientes; desistentes em nota |
| P4 | "SC" e "Sem CPC" pareciam a mesma categoria | "Sem conceito (SC)" e "Não avaliado" |
| B1 | Só vagas ofertadas, sem medida de alunos | Ingressantes presenciais e ingressantes por 100 jovens, com máscara de células pequenas |

- Validação: 66 testes Python e 114 nós do dbt passando; outputs regerados no laboratório. Commits `eadc4c8` e `b93d2dc`.

**C4. Confirmação das ressalvas da fonte na Silver**
- Pedido: verificar com consulta direta se as anomalias vinham do pipeline ou da fonte.
- Resposta (`scripts/diagnostico.sql`):
  - B2: nenhum curso com FIES ou ProUni vazio; a oscilação anual vem da declaração das IES (ex.: 642, 447, 1.539 e 499 matrículas FIES numa mesma IES de 2021 a 2024).
  - P3: o pico de 2023 na rede pública vem de UNEMAT (6.230 desvinculados) e UFMT (4.768), contra cerca de 1.200 nos anos vizinhos.
  - B1: em São José dos Quatro Marcos, uma faculdade declara 937 vagas em Pedagogia com 0 ingressantes.
  - Filtros da consulta passaram a usar códigos, porque o PowerShell altera a codificação de acentos ao enviar o arquivo ao `psql`.
- Validação: rodado no laboratório; ressalvas registradas no README. Commits `a614772` e `69892f6`.

## 3. Integração do BI

**C5. Acesso do BI ao DW com menor privilégio**
- Pedido: integrar pgAdmin e Superset ao DW lendo só a camada publicada.
- Resposta: usuário `dh_bi_reader`, somente leitura e restrito ao schema `gold`; pgAdmin em `127.0.0.1:5433`; Superset em Docker ligado à rede `datahack_warehouse` com host `warehouse`.
- Validação: `select count(*) from gold.b1_desertos_municipio` retornou 141; os demais schemas negam acesso a esse usuário.

**C6. Dataset do Superset retornando vazio**
- Pedido: diagnosticar cards com "Metadados" no Superset.
- Resposta: "Metadados" é a tradução de "No data"; a consulta roda, mas o dataset aponta para outro banco ou schema. SQL do dataset B1 e valores de conferência entregues.
- Validação: valores conferidos no pgAdmin (141 municípios, 101 sem oferta, 20,57 vagas por 100 jovens).

**C7. Validação de números gerados por outra IA**
- Pedido: comparar com a Gold as respostas do chat do Superset usadas por um colega.
- Resposta:

| Indicador | Chat do Superset | Gold publicada |
|---|---|---|
| B1: municípios sem vaga presencial | 76 | 101 |
| B1: vagas por 100 jovens | 12,4 | 20,57 |
| P5: ingressantes em licenciatura | 2.887 | 7.928 |
| P5: proficiência no Enade | "vazia" | 59,3% |

  Conclusão: o Superset lia outra carga. A tabela `controle_atualizacao` ganhou arquivos e linhas disponíveis por fonte, porque "0 linhas na última execução" era interpretado como fonte vazia.
- Validação: números do chat rejeitados; reimportação feita a partir da `main`. Commits `25367d1` e `598cf69`.

## 4. Documentação

**C8. Documentação alinhada à versão publicada**
- Pedido: atualizar README e documentos técnicos com o estado final.
- Resposta: README com resultados, ressalvas da fonte, papéis das camadas Gold e `ops` e guia de conexão de BI; arquitetura, estratégia e runbook atualizados.
- Validação: revisado pelo autor. Commit `69892f6`.

## O que foi aproveitado ou corrigido

| Tipo | Item |
|---|---|
| Corrigido na Gold | Perda de cursos na soma de ProUni e financiamento; rótulos de CPC; B1 com ingressantes |
| Corrigido no dashboard | Séries misturadas no P1; etapa errada no funil P5 |
| Corrigido no CI | `dbt debug` sem depender de `git` |
| Rejeitado | Números do chat do Superset, por divergirem da Gold testada |
| Confirmado na fonte | Ressalvas de B1, P3 e B2 com consulta direta na Silver |
