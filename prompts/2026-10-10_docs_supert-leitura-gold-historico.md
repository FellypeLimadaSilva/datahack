# Histórico dos prompts: correção da gold no Superset (10/10/2026)

Registro, em ordem, de tudo que foi pedido nesta sessão, o que foi feito em cada pedido e o resultado.
Branch de trabalho: `deploy`. Repositório do evento (`origin`): FellypeLimadaSilva/datahack. Repositório da Railway (remote `deploy`): mauriciobalboa/datahack-deploy.

## Resumo em uma página

| # | Pedido | Resultado |
|---|---|---|
| 1 | Ver se o Superset lê tabela/schema antigo da gold | Não lê. Superset e datasets estão certos; o **banco** do laboratório estava desatualizado (B1 vazio, IBGE `failed`) |
| 2 | (mensagem colada) Números do chat não batem com a gold; conferir conexão, datasets e card B1 = 101 | Conexão e datasets confirmados. O 101 só aparece depois de atualizar a gold |
| 3 | Fazer pull da `main` (estava usando a `develop`) | Merge limpo de `origin/main` no `deploy` (`51270c6`) |
| 4 | Rodar o pipeline | Rejeitado pelo portão: faltam os brutos do INEP. Gold anterior intacta. IBGE carregou (987 linhas) |
| 5 | Como usar o banco do outro PC / Railway em 2 contas? | Não precisa: a Railway recarrega a gold dos `outputs/*.parquet` do Git |
| 6 | Deixar esta máquina pronta para receber os dados | Criado `dh.ps1 carregar-gold`; banco local atualizado e conferido (101, 20,57, 18,63) |
| 7 | Push feito, fazer pull e merge | Merge `e809093` + nova carga; IBGE `success` |
| 8 | Contexto para outro chat corrigir a prod | Texto de handoff entregue no chat |
| 9 | Documentar todos os prompts em `.md` | Este arquivo |

---

## Prompt 1: verificar se o Superset lê gold antiga

> "verique para mim, se o meu supert nao esta lendo uma table ou schema antiga da camada gold, pois tem aiguns dados que estao sendo apresentados errados"

**O que foi verificado (somente leitura)**
- Bundle (`superset/bundle/...`): os 13 datasets têm `schema: gold`, nenhum é virtual (sem SQL próprio) e o banco é `Warehouse · gold` (`dh_bi_reader@warehouse:5432/datahack`).
- Metadados do Superset em execução: 1 conexão, 13 datasets em `gold`, 58 gráficos no dashboard. Há 8 gráficos "Visão geral" **órfãos**, fora do dashboard, sem dataset: resíduos de um import anterior, sem efeito na tela.
- Warehouse: só os schemas `gold` (13 tabelas) e `ops`. Nenhuma tabela antiga ou duplicada.
- Contagens de linhas do `gold` iguais às de `outputs/*.csv`.
- Cache do Superset: `NullCache` (Refresh sempre mostra o dado atual).

**Achados**
- `gold.b1_desertos_municipio` com **0 linhas**, o que deixa os 8 gráficos do B1 vazios ou errados.
- `gold.controle_atualizacao`: `ibge_populacao_idade_mt` com status `failed`.
- O dbt não encontrou a tabela de população do IBGE; as linhas "0" da coluna `linhas_ultima_execucao` significavam "nenhum arquivo novo", mas eram lidas como "fonte vazia".

**Conclusão:** o Superset estava correto; o banco do laboratório tinha carga antiga.

---

## Prompt 2: mensagem colada durante a execução

Conteúdo colado (comparação feita por outra pessoa): números do chat do Superset divergiam da gold oficial:

| Indicador | Chat do Superset | Gold oficial |
|---|---|---|
| B1: municípios sem vaga presencial | 76 | 101 |
| B1: jovens de 18 a 24 anos | ~476 mil | 397.671 |
| B1: vagas presenciais | ~59 mil | 81.795 |
| B1: vagas por 100 jovens | ~12,4 | 20,57 |
| P5: ingressantes em licenciatura | 2.887 | 7.928 |
| P5: desistem / concluem (de cada 100) | 47,8 / 15,2 | 53,7 / 31,4 |
| P5: proficiência no Enade | "100% vazia" | 59,3% (69 cursos, 1.014 participantes) |
| Fonte IBGE | "falha" | success, 987 linhas |

Também citava o commit **25367d1** (`controle_atualizacao` com arquivos e linhas por fonte) e orientava `git pull` + `.\scripts\dh.ps1 pipeline`.

Pedido do usuário (texto fora do bloco colado):
> Conectar o Superset no banco do PC do laboratório com `dh_bi_reader`, banco `datahack`; conferir que todos os datasets estão em Database `datahack` e Schema `gold`; dar Refresh; o card do B1 deve mostrar 101.

**Resultado:** conexão e datasets já estavam corretos. Constatado que o commit 25367d1 **não estava** no branch `deploy` (só em `origin/main`). O 101 depende de atualizar a gold, não de reconfigurar o Superset.

---

## Prompt 3: pull da main

> "faz o pull do novo na main, dos dados, estava usando os dados da develop, pois isto nao veio para mim"

**Feito:** `git fetch origin`; a `main` tinha 14 commits novos (inclui 25367d1) e o `deploy` tinha 7 próprios. Merge de `origin/main` no `deploy` sem conflitos: commit `51270c6`. O trabalho do `deploy` (Superset, chat, Railway) foi preservado.

**Observação:** a `main` já trazia `outputs/b1_desertos_municipio` com 141 municípios e uma tabela nova, `s1_fator_social_desistencia`. O IBGE vem de uma URL do SIDRA (tabela 9514), não de arquivo local.

---

## Prompt 4: rodar o pipeline

> "rode a pipeline"

**Feito:** `.\scripts\dh.ps1 pipeline`.

**Resultado**
- IBGE carregou: 987 linhas (antes `failed`).
- **Publicação rejeitada pelo portão de qualidade**: `bronze.censo_cursos`, `censo_ies`, `trajetoria` e `cpc` não existem, porque `data/landing/inep/` está vazia (os brutos do INEP, ~450 MB, não vão pelo Git e não estavam em Downloads).
- A gold anterior foi mantida intacta; nada foi perdido.

**Alternativas apresentadas:** obter os arquivos do INEP (`dh.ps1 import-downloads`) ou usar o Plano B (`dh.ps1 planilhas`).

---

## Prompt 5: banco em outro PC e Railway com 2 contas

> "o banco esta sendo feito em outro pc, como eu poderia fazer para usar o banco do outro pc para usar neste aqui? se eu vou subir tudo na railway, ou eu subo o banco dele na railway e faço gate para usar no meu railway? serao 2 contas diferentes"

**Resposta:** não é preciso acessar o banco do outro PC nem criar gate entre contas. O fluxo do projeto (`deploy/README.md`):
1. O outro PC roda o pipeline e faz push de `outputs/*.parquet` (versionados, ~608 KB).
2. No deploy do Superset, `deploy/superset/load_gold.py` recria o schema `gold` do Postgres da Railway a partir dos parquets, numa única transação.
3. Expor o Postgres do outro PC exigiria proxy TCP público entre contas e criaria dependência de a máquina dele estar ligada.

---

## Prompt 6: preparar esta máquina para receber os dados

> "deixe esta maquina preparada para receber os dados, o outro dev ja esta fazendo o push para merge"

**Criado**
- `scripts/load_outputs_local.py`: lê `outputs/*.parquet` e recria o schema `gold` do banco local numa transação única, com `GRANT SELECT` ao `dh_bi_reader`.
- `scripts/dh.ps1`: novo comando `carregar-gold` (e linha de ajuda).
- Nota de memória do projeto com o fluxo (`project-gold-vem-do-outro-dev`).

**Teste:** 14 tabelas carregadas. Conferência com `dh_bi_reader`: sem oferta = 101 (de 141), jovens 397.671, vagas 81.795, vagas/100 jovens 20,57, P5 ingressantes 7.928, desistem/concluem 53,73 / 31,44, Enade 59,27% (1.014 participantes), concluem proficientes 18,63. Todas as colunas usadas pelos datasets do bundle continuam existindo.

**Fluxo a partir daí**
```powershell
git fetch origin
git merge origin/main
.\scripts\dh.ps1 carregar-gold
```

---

## Prompt 7: push feito, pull e merge

> "ja foi feito o push, faça o pull e merge"

**Feito:** a `main` tinha 1 commit novo (`598cf69`, "outputs atualizados para o deploy", só `outputs/`). Merge `e809093` sem conflitos e nova carga com `carregar-gold`. `controle_atualizacao` mostra `ibge_populacao_idade_mt` como `success` (987 linhas); B1 sem oferta = 101.

---

## Prompt 8: contexto para corrigir a produção em outro chat

> "me passa um contexto do que feito, se ja esta ok, para usar em outro chat para eu fazer a correção na prod"

**Entregue:** bloco de contexto com problema, causa, o que foi feito localmente, como a produção é alimentada e passos para a prod. Pontos principais:
- Nada foi feito na Railway (nenhum push no remote `deploy`).
- O `sync-evento.yml` segue por padrão a branch `develop` (variável `EVENT_BRANCH`), que não tinha as correções; definir `EVENT_BRANCH=main` ou confirmar a `develop`.
- Depois: `git push deploy deploy`; se os gráficos não mudarem, `FORCE_REIMPORT=1`.
- Conferir nos logs `gold.b1_desertos_municipio: 141 linhas` e, no dashboard, B1 = 101, vagas/100 jovens = 20,57, concluem proficientes = 18,6.

---

## Prompt 9: este documento

> "faça uma documentação sobre todos meus prompts em .md desta janela de contexto"

---

## Estado ao final da sessão

- **Banco local:** gold atualizada com os `outputs/` da `main` (até `598cf69`), conferida.
- **Branch `deploy`:** contém merges `51270c6` e `e809093`.
- **Sem commit:** `scripts/dh.ps1`, `scripts/load_outputs_local.py` e este arquivo. O arquivo `chatbot/app/settings_store.py` aparece deletado sem commit desde antes da sessão; não commitar por engano.
- **Produção (Railway):** não tocada e não verificada.
- **Pendências:** definir a branch do `sync-evento`; `git push deploy deploy`; criar dataset e gráfico para `s1_fator_social_desistencia`, se for usá-la no dashboard; não usar números do chat de IA no pitch.
