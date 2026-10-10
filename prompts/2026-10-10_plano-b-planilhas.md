# Conversa com IA · Plano B sem banco de dados (planilhas)

| | |
|---|---|
| Data | 10/10/2026 |
| Ferramenta | Claude Code (Claude Sonnet 5.5), app desktop |
| Projeto | DataHack UNIVAG 2026 · Rota do Diploma (`datahack/`) |
| Fase | Contingência |
| Prompts nesta janela de contexto | 2 (reproduzidos abaixo, sem edição) |
| Índice | linha correspondente em [`README.md`](README.md) |

Esta janela de contexto tem **dois prompts**. Cada um aparece na íntegra, seguido do que a IA entendeu, fez, verificou e do que ficou de fora.

---

## Prompt 1 · Dashboard funcionando sem banco, só com planilhas

> é o seguinte, este projeto que to fazendo, é o plano B nosso, ele é mais enxutado, tudo estara embedado no superset, e vamos continuar desta forma, porem preciso do seguinte, por ser um plano B, preciso que este mesmo sistema, funcione sem banco de dados, de forma atraves de planilhas, pois se o bd der problema, teremos a opção de importação planilhas no geral, todos os tipos de arquivo de planilha

### Como a IA interpretou

- "Este mesmo sistema" = o dashboard Superset já pronto (9 abas, 54 gráficos, 8 filtros) e o chat com IA embutido nele, **sem reescrever nada**: só trocar a fonte de dados.
- "Sem banco de dados" = sem o Postgres (warehouse). O Superset precisa de *algum* SQL por baixo, então a fonte passou a ser um arquivo SQLite local, montado a partir das planilhas e aberto só para leitura.
- "Todos os tipos de arquivo de planilha" = csv, tsv, xlsx, xlsm, xls, xlsb, ods, parquet, json/jsonl, e esses mesmos dentro de zip/gz.
- Não foi pedido, mas é a condição para o plano B valer: tem de **subir mesmo sem o banco e sem a rede do warehouse**, e a pasta vazia não pode deixar o painel vazio (usa as exportações da Gold já existentes em `outputs/`).

### O que foi feito

| Peça | Arquivo | Função |
|---|---|---|
| Carregador | `superset/docker/planilhas.py` | Lê qualquer formato, reconhece qual planilha é qual das 13 tabelas (pelo nome do arquivo/aba ou pelas colunas), acha o cabeçalho mesmo com títulos acima, converte vírgula decimal, `%`, `R$`, `sim/não`, e grava o SQLite de forma atômica. Modos `--check`, `--watch` e `--modelo` |
| Contrato de colunas | `superset/build_bundle.js` → `bundle/contrato_planilhas.json`, `planilhas/CONTRATO.md` | Gerado da mesma definição dos datasets, então não diverge do dashboard |
| Fonte alternativa | `superset/docker/reimport.py` (`DATA_SOURCE=planilhas`) | Aponta os 13 datasets para o SQLite (sem schema `gold`), conexão só leitura, e troca o aviso da aba "Fontes e metodologia" para "modo planilhas" |
| Stack sem banco | `superset/docker-compose.planilhas.yml`, `docker/init.sh`, `Dockerfile` | Superset sozinho (metadados em SQLite), sem rede externa; bibliotecas `openpyxl`, `xlrd`, `pyxlsb`, `odfpy` |
| Comandos | `superset/up.ps1 -Planilhas`, `scripts/dh.ps1 planilhas` | Sobem o Plano B; o modo normal e o Plano B usam a mesma porta, um derruba o outro |
| Chat | `chatbot/app/{db,sql_guard,knowledge,prompts,llm}.py`, `chatbot/docker-compose.planilhas.yml` | O chat passa a ler o mesmo SQLite: dialeto SQLite, remove `gold.` do SQL, só aceita `SELECT`, arquivo aberto só leitura |
| Testes | `superset/tests/test_planilhas.py`, `chatbot/tests/test_sql_guard.py` | Formatos, funções de conversão e guarda de SQL |
| Documentação | `superset/planilhas/LEIA-ME.md`, `superset/README.md`, `chatbot/README.md`, `prompts/README.md` | Uso, limites e contrato |

Uso: `.\scripts\dh.ps1 planilhas`; soltar arquivos em `superset/planilhas/` recarrega o painel em cerca de 10 s; com a pasta vazia usa `outputs/`.

### Como foi verificado

- **Formatos:** as tabelas da Gold foram regravadas em xlsx (com 3 linhas de título), CSV `;` com vírgula decimal em cp1252, ods, xls, parquet, json, jsonl, tsv.gz, zip e CSV com BOM/maiúsculas. As 11 tabelas com dados voltaram idênticas à Gold; arquivos de lixo (`~$`, `_rascunho`, `.txt`, nome ambíguo) foram ignorados. Mais 16 casos de conversão numérica e 8 de booleano.
- **Dashboard em SQLite:** as 9 abas abriram com 53 chamadas de dados, todas com status 200 e zero erros; 6 gráficos vazios, esperado porque a tabela B1 não tem linhas na Gold hoje.
- **Equivalência com o Postgres:** as 53 consultas capturadas do front-end foram reexecutadas no Superset normal e no Plano B: **48 idênticas, 5 com os mesmos valores em outra ordem de empate, 0 erros**.
- **Recarga automática, arquivo corrompido e remoção da planilha:** testados no container; corrompido vira aviso, remover a planilha volta para a Gold exportada.
- **Chat:** 46 testes do guarda de SQL (incluindo o dialeto SQLite); consulta real ao SQLite dentro do container; `DROP` e `ATTACH` bloqueados.
- **PowerShell 5.1:** sintaxe de `up.ps1` e `dh.ps1` e as funções auxiliares do `up.ps1` testadas.

### Correções de rumo durante o trabalho

- A API de dados do Superset não aceita montar a consulta só com o id do gráfico; a validação passou a capturar as consultas que o navegador envia e reexecutá-las nas duas instâncias.
- `pandas 2.0.3` da imagem não tem `DataFrame.map` nem escreve `.xls`; o teste usa `applymap` e `xlwt` direto.
- No Windows PowerShell 5.1, redirecionar o stderr de um `.exe` vira erro fatal; o `up.ps1` usa uma função `Dk` que isola isso.
- O Git Bash reescreve caminhos de `docker exec`; usado `MSYS_NO_PATHCONV=1`.
- O `up.ps1` precisou respeitar `SUPERSET_PORT` do `superset/.env`, porque outra sessão passou a usar um gateway (nginx) na porta 8088 e o Superset na 8090.

### Limites declarados

- O Plano B **não recalcula nada**: mostra as 13 tabelas da Gold. Se só restarem os microdados brutos do INEP, não calcula a Gold a partir deles.
- `scripts\dh.ps1 planilhas` e `superset\up.ps1 -Planilhas` **não foram executados ao vivo** (derrubariam o stack em uso); só o compose direto e as funções do script foram testados. Falta rodar uma vez.
- O chat do Plano B foi testado só com consultas diretas ao SQLite, sem chamar a DeepSeek.
- Nenhum commit foi feito.

---

## Prompt 2 · Documentar os prompts desta janela

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

### O que foi feito

Este arquivo. Segue a convenção da pasta (`prompts/`): um `.md` por sessão, com o objetivo, o que foi aproveitado e o que foi corrigido, e a linha correspondente no índice `prompts/README.md` (adicionada no Prompt 1 com o nome `2026-10-10_plano-b-planilhas.md`).

### Observações

- Só existem **dois prompts** do usuário nesta janela; o restante do texto que a IA viu (arquivos do projeto, saídas de comandos, avisos do sistema) não é prompt e não está reproduzido aqui.
- Esta janela de contexto é separada das outras sessões do projeto (remodelagem ELT, chat DeepSeek, gateway). Para o histórico completo, cada sessão tem a sua linha no índice.
- A regra da pasta pede a conversa **exportada** do próprio Claude Code (`.md`, `.txt`, `.pdf` ou `.json`). Este arquivo é um resumo escrito a partir dela e não substitui a exportação; se a banca exigir a conversa literal, exporte esta sessão e guarde ao lado, com o nome `2026-10-10_HHMM_claude_plano-b-planilhas.md`.
