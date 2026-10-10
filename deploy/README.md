# Deploy na Railway (dashboard, chat e banco)

Tudo roda na Railway, em um projeto com 4 serviços. Só o **gateway** tem domínio público.

```
navegador ─► gateway (nginx, público) ─┬─► superset  (rede privada :8088) ─┐
                                       └─► chatbot   (rede privada :8099) ─┼─► Postgres (gold, papel dh_bi_reader somente leitura)
```

| Serviço | Config-as-code | Dockerfile | Volume |
|---|---|---|---|
| Postgres | plugin da Railway | | (do plugin) |
| `superset` | `deploy/railway.superset.json` | `deploy/superset.Dockerfile` | não |
| `chatbot` | `deploy/railway.chatbot.json` | `deploy/chatbot.Dockerfile` | **sim, em `/data`** (guarda a chave da DeepSeek) |
| `gateway` | `deploy/railway.gateway.json` | `deploy/gateway.Dockerfile` | não |

Os nomes dos serviços precisam ser exatamente `superset`, `chatbot` e `gateway` (os endereços `*.railway.internal` dependem deles).
As variáveis estão em [`.env.example`](.env.example).

## Passo a passo (primeira vez)

1. **Projeto**: railway.com → New Project → **Deploy PostgreSQL**.
2. **Serviços**: New → GitHub Repo → este repositório, três vezes. Renomeie cada um (`superset`, `chatbot`, `gateway`) e em *Settings → Config-as-code* aponte o arquivo da tabela acima. Branch: `main`.
3. **Variáveis**: cole as de cada serviço (`.env.example`). Gere `SUPERSET_SECRET_KEY` e escolha as senhas.
4. **Volume do chatbot**: serviço `chatbot` → *Volumes* → mount path `/data`. Variável `RAILWAY_RUN_UID=0` (o volume nasce como root).
5. **Domínio**: só no `gateway` → *Settings → Networking → Generate Domain*. Copie a URL `https://….up.railway.app` para `CHAT_PARENT_ORIGINS` do `chatbot`.
6. **Ordem do primeiro deploy**: Postgres → `superset` (leva alguns minutos: cria os databases, carrega a gold e importa o dashboard) → `chatbot` → `gateway`.
7. Abra o domínio. Entre em **Login** como `admin` (senha = `SUPERSET_ADMIN_PASSWORD`) → *Settings → Manage → Configurações do chat (IA)* → cole a chave da DeepSeek e **Salvar e testar**.

## Como o banco é alimentado

O pipeline (INEP + IBGE → dbt) roda no laboratório e gera `outputs/*.parquet` (versionados no Git). A cada deploy do `superset`, `deploy/superset/load_gold.py`
recria o schema `gold` **em uma única transação** com esses arquivos e libera `SELECT` ao `dh_bi_reader`. Resultado: `git push` com `outputs/` novo → deploy → dashboard atualizado.
O `chatbot` monta o dicionário de dados do mesmo bundle e de `outputs/_indicadores.json` (embutidos na imagem).

## Alimentação pelo repositório do evento

`.github/workflows/sync-evento.yml` busca a branch do repo do evento (padrão: `develop` de `FellypeLimadaSilva/datahack`) a cada 15 minutos e faz merge aqui;
o push dispara o deploy da Railway. Ajuste por *Settings → Secrets and variables → Actions*:

| Nome | Tipo | Para quê |
|---|---|---|
| `EVENT_BRANCH` | variável | branch do evento a seguir (padrão `develop`) |
| `EVENT_REPO` | variável | URL do repo do evento, se mudar |
| `SYNC_TOKEN` | secret | PAT (`repo` + `workflow`); necessário se o evento alterar `.github/workflows` |

Conflito no merge: o job falha e abre uma issue. Os arquivos desta pasta (`deploy/`) não existem no repo do evento, então não conflitam.

## Teste local (sem Railway)

```bash
docker build -f deploy/superset.Dockerfile -t dh-superset .
docker build -f deploy/chatbot.Dockerfile  -t dh-chatbot  .
docker build -f deploy/gateway.Dockerfile  -t dh-gateway  .
```
Suba os três numa rede com um `postgres:16-alpine`; para o gateway local use `-e DNS_RESOLVER=127.0.0.11 -e SUPERSET_HOST=<nome> -e CHAT_HOST=<nome>`.
