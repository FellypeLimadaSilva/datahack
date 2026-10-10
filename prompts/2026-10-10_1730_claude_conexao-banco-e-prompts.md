# Sessão: como o sistema se conecta ao banco e registro dos prompts

- **Ferramenta:** Claude Code (Claude Sonnet 5.5)
- **Data:** 2026-10-10
- **Quem usou:** Mauricio Balboa
- **Fase:** Documentação
- **Objetivo:** entender como o dashboard e o chat com IA se conectam ao banco e registrar os prompts da sessão
- **Resultado:** só explicação e este registro. Nenhum arquivo de código foi alterado.

> Esta janela de contexto contém **dois prompts**. O trabalho anterior (chat DeepSeek, Plano B com planilhas,
> filtros interativos) aconteceu em outras sessões e está registrado nos arquivos vizinhos desta pasta.

## Contexto lido pela IA antes de responder

`superset/docker/reimport.py`, `superset/docker-compose.yml`, `chatbot/app/db.py` e, por busca, as referências
a `dh_bi_reader` em `infra/postgres/bootstrap.sql`, `superset/build_bundle.js`, `superset/up.ps1`,
`chatbot/docker-compose.yml`, `docs/arquitetura.md` e `superset/README.md`.

---

## Prompt 1

> como foi conectado ao banco este sistema?

**Resposta resumida da IA**

O dashboard (Superset) e o chat com IA leem o mesmo banco, o warehouse PostgreSQL do repositório, com o mesmo
papel somente leitura `dh_bi_reader`, restrito ao schema `gold`.

1. **Papel no banco** (`infra/postgres/bootstrap.sql`): `default_transaction_read_only = on`,
   `statement_timeout = 120s`, `search_path = gold`, `GRANT SELECT` só em `gold`; `bronze`, `silver`, `ops` e
   `gold_candidate` são revogados. A publicação da Gold refaz o `GRANT`, por isso o dashboard acompanha a nova
   versão sem reimportar.
2. **Rede e senha:** o container do Superset entra na rede externa `datahack_warehouse` e conecta em
   `warehouse:5432`. A senha vem do `.env` da raiz (`dh.ps1 env`), é copiada pelo `superset/up.ps1` para
   `superset/.env` (fora do Git) e chega ao container como `WAREHOUSE_BI_PASSWORD`. Nunca vai no pacote do
   dashboard: `build_bundle.js` grava só `placeholder` na URI.
3. **Conexão no Superset** (`superset/docker/reimport.py`): no boot monta
   `postgresql+psycopg2://dh_bi_reader:<senha>@warehouse:5432/datahack`, cria ou atualiza o objeto `Database`
   (`set_sqlalchemy_uri`) e importa o dashboard. Cada dataset é uma tabela `gold.*`. Um segundo Postgres, só de
   metadados (`SUPERSET_DB_URI`), guarda o estado interno do Superset.
4. **Conexão do chat** (`chatbot/app/db.py`): `psycopg` direto, com as mesmas variáveis `WAREHOUSE_*` e
   `search_path=gold`. Cada consulta roda em transação `read_only`, com `statement_timeout` de 10 s, depois do
   validador `sql_guard.py`; o papel do banco é a defesa final.
5. **Plano B:** com `DATA_SOURCE=planilhas`, os dois trocam o Postgres por um SQLite montado a partir das
   planilhas, aberto com `mode=ro` e com um autorizador que só aceita `SELECT`.

**O que foi aproveitado ou corrigido:** nada a corrigir; a resposta foi conferida diretamente no código.

---

## Prompt 2

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**Resposta resumida da IA**

Criou este arquivo seguindo o formato e o nome (`AAAA-MM-DD_HHMM_ferramenta_tema.md`) da pasta `prompts/`, e
acrescentou a linha correspondente ao índice em `prompts/README.md`. Informou que a janela tem apenas dois
prompts e que o trabalho das sessões anteriores está nos outros arquivos da pasta.
