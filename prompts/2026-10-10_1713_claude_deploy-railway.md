# Deploy na Railway: documentação dos prompts

- **Ferramenta:** Claude Code (Claude Sonnet 5.5), aplicativo desktop, aba Code
- **Quem usou:** Mauricio Balboa
- **Data:** 2026-10-10
- **Fase:** Entrega (publicação)
- **Resultado final:** dashboard + chat com IA + Postgres no ar em `https://rotadodiploma.up.railway.app`, a partir de um repo privado alimentado pelo repo do evento.

Os prompts abaixo estão **na ordem em que foram enviados**, com o texto original (erros de digitação preservados), o que o Claude fez e o que mudou ao longo do caminho.

---

## Prompt 1: pedido inicial

> seguinte, preciso preparar para o deploy agora, vou hospedar o back end na railway e o front na vercel, preciso que faça uma analise do que hospedar em cada, preciso que crie os repo privado na minha conta do git, para o deploy, e como vou fazer o gate para o back alimentar o front, e preciso que tambem meu repos seja alimentado pelo repos do evento, se possivel

**O que o Claude fez**
- Entrou em modo de planejamento e mapeou o repositório (um agente de exploração leu `README`, `docs/`, `chatbot/`, `gateway/`, `superset/`, `dashboard/`, `.github/`, tamanhos).
- Constatou que **não havia nada pronto para deploy**: sem `Procfile`/`vercel.json`, bind mounts no compose, `host.docker.internal` no nginx, chatbot e gateway ainda não commitados e **nenhum front estático** (o `dashboard/` é Streamlit e o painel principal é Apache Superset, um app Python com banco, que não roda na Vercel).
- Identificou que o `origin` é o repo do evento (`FellypeLimadaSilva/datahack`) e que a `develop` está 10 commits atrás da `main`.
- Fez perguntas antes de planejar (prompt 2).

---

## Prompt 2: respostas às perguntas de escopo

O Claude perguntou: qual é o "repo do evento", quantos repos criar, como criar (gh CLI) e como seria o front na Vercel. Respostas:

> é este repo do evento, porem estou usando a branch develop

> 2 repos: backend + frontend *(opção escolhida)*

> Instalo o gh CLI e faço login *(opção escolhida)*

> se hospedar o front e o bd na railway, ela aguenta?

**O que o Claude fez**
- Registrou que a pergunta sobre o front virou outra pergunta: se a Railway aguentaria front e banco.
- Respondeu no plano: **sim**, os dados são pequenos (`outputs/` = 438 KB) e o peso é o Superset (~1 a 2 GB de RAM).

---

## Prompt 3: mudança de plano

> vamos mudar o plano, vou hospedar tudo na railway, front, back e bd, preciso saber como farei isto

**O que o Claude fez / decidiu**
- Tirou a Vercel do desenho. O "front" passou a ser a própria interface do Superset com o botão flutuante do chat, tudo no mesmo domínio (mantém `location.origin`, cookie de admin e iframe sem CORS).
- Trocou os 2 repos por **1 repo privado** (o chatbot precisa de arquivos de `superset/` e `outputs/`, então o contexto de build é a raiz).
- Escreveu e submeteu o plano (aprovado por você): 4 serviços na Railway (Postgres, `superset`, `chatbot`, `gateway`), só o `gateway` público, carga da gold no banco a cada deploy, workflow de sincronização com o repo do evento.

---

## Aprovação do plano

Você aprovou o plano e a implementação começou. Antes de qualquer deploy, o Claude:
- Criou `deploy/` com os três Dockerfiles, `load_gold.py`, template do nginx, `.env.example` e `README.md`.
- Testou tudo **localmente** numa rede Docker simulando a Railway (Postgres, Superset, chat e gateway): a gold carregou (13 tabelas), o dashboard abriu pelo gateway, o usuário `dh_bi_reader` ficou somente leitura e os 74 testes do chatbot passaram.
- **Correção encontrada no teste:** o uvicorn com `--host ::` ouvia só IPv6 (o gateway recebeu 502). Criou `deploy/chatbot/serve.py` com socket dual-stack.
- Commitou seu trabalho pendente em `develop` e os arquivos de deploy numa branch `deploy`.

---

## Prompt 4: login no GitHub

> ja fiz o auth login, pode fazer

**O que o Claude fez**
- Instalou o `gh` CLI (winget) e abriu o login numa aba do seu terminal; você concluiu no navegador.
- Criou o repo privado `mauriciobalboa/datahack-deploy`, empurrou a branch `deploy` como `main`, desativou o `ci.yml` herdado (pesado) e disparou o `sync-evento.yml` (sucesso em 12 s).
- Simulou o merge da `main` do evento: limpo, sem conflitos.
- Deixou em aberto duas decisões suas: seguir `develop` ou `main` do evento (`EVENT_BRANCH`) e criar o `SYNC_TOKEN`.

---

## Prompt 5: CLI da Railway

> rode para eu conectar no cli da railway, ai voce faz o deploy

**O que o Claude fez**
- O `npm install -g @railway/cli` falhou com 403 (política de segurança) e o winget não tem o pacote.
- Perguntou como seguir (prompt 6).

## Prompt 6: resposta à pergunta sobre a instalação

> Baixar o binário do GitHub (Recomendado) *(opção escolhida)*

**O que o Claude fez**
- Baixou o release oficial `railway-v5.64.2` para uma pasta isolada e **conferiu o SHA-256** contra o hash publicado pelo GitHub.
- **Problema:** a primeira instalação ficou só no ambiente isolado do shell do Claude; o seu terminal respondia "acesso negado". Reinstalou via script rodado no seu terminal em `C:\Users\mauricio.balboa\railway-cli\`.
- O Windows **bloqueou a alteração do PATH** do usuário. O Claude não contornou: usa o executável pelo caminho completo.

## Prompt 7: nova tentativa

> Tentar novamente

**O que o Claude fez:** repetiu o login do Railway CLI numa aba do terminal (com o caminho completo, já que a tentativa anterior havia sido recusada pelo hook por usar variável de ambiente).

## Prompt 8: login concluído

> logado papai

**O que o Claude fez**
- Confirmou o login e criou o projeto `datahack-rota-do-diploma`, o Postgres e os serviços `superset`, `chatbot` e `gateway` ligados ao repo privado.
- Gerou as senhas e a chave do Superset localmente e as gravou **direto nas variáveis da Railway** (não aparecem no Git nem no chat).
- Problemas e correções durante o deploy:
  | Problema | Causa | Correção |
  |---|---|---|
  | `railway environment edit` respondia "No changes to apply" | comando não aplicou as mudanças nesta versão | variáveis via `railway variable set`, build via API GraphQL |
  | Mutation de `railwayConfigFile` recusada | config-as-code (`railway.json`) está deprecado | apagou os `railway.*.json`; Dockerfile definido por `RAILWAY_DOCKERFILE_PATH` |
  | Build falhou com Railpack ("No start command") | não existe builder `DOCKERFILE` no enum da API | variável `RAILWAY_DOCKERFILE_PATH` por serviço |
  | `redeploy` reaproveitava a configuração antiga | redeploy copia o snapshot do deploy anterior | nova implantação via `serviceInstanceDeployV2` |
  | `volume add` do CLI deu *panic* | falta de IDs explícitos | repetiu com `--service` e `--environment` em IDs |
  | Superset ficou "Deploying" e o gateway deu 502 | healthcheck usa `PORT`, que não estava definido | `PORT=8088` no `superset` |
- Teste final pela URL pública: dashboard 200, 58 gráficos para visitante anônimo, 13 tabelas gold carregadas, chat acessível pelo gateway, configuração do chat restrita a admin.

## Prompt 9: link para a apresentação

> gere um link para mim para usar na apresentação

**O que o Claude fez:** verificou que o domínio do gateway abria direto no dashboard e entregou o link `https://gateway-production-96e1.up.railway.app`, com avisos (chave da DeepSeek ainda por colar, primeira carga lenta, plano C obrigatório no evento).

## Prompt 10: link mais simples

> deixe o mais simples

**O que o Claude fez**
- Renomeou o domínio do gateway para **`https://rotadodiploma.up.railway.app`**.
- Atualizou `CHAT_PARENT_ORIGINS` do chat para o novo endereço (senão o CSP `frame-ancestors` bloquearia o iframe do chat), esperou o redeploy e testou: dashboard 200 e CSP correto. O endereço antigo saiu do ar.

## Prompt 11: esta documentação

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**O que o Claude fez:** gerou este arquivo e a linha correspondente no índice `prompts/README.md`.

---

## Resumo das decisões que vieram dos seus prompts

| Decisão | Origem |
|---|---|
| Repo do evento = `origin` (`FellypeLimadaSilva/datahack`), seguindo a `develop` | Prompt 2 |
| Tudo na Railway, Vercel descartada, 1 repo privado | Prompt 3 |
| `gh` CLI para criar o repo privado | Prompt 2 e 4 |
| Railway CLI pelo binário oficial do GitHub (hash conferido) | Prompt 6 |
| Link público curto: `rotadodiploma.up.railway.app` | Prompt 10 |

## O que foi entregue

- `deploy/` no repo privado `mauriciobalboa/datahack-deploy`: `superset.Dockerfile`, `chatbot.Dockerfile`, `gateway.Dockerfile`, `superset/load_gold.py`, `gateway/nginx.conf.template`, `chatbot/serve.py`, `.env.example`, `README.md`.
- `.github/workflows/sync-evento.yml`: traz a branch do repo do evento a cada 15 minutos (padrão `develop`).
- Projeto Railway com Postgres, `superset`, `chatbot` (com volume em `/data`) e `gateway`.

## Pendências registradas no fim da sessão

- Colar a chave da DeepSeek em Settings → Configurações do chat (IA) e fazer uma pergunta de teste: **o chat ainda não foi testado com resposta real**.
- Decidir se o sync segue `develop` ou `main` do evento (`EVENT_BRANCH`) e criar o `SYNC_TOKEN` (token pessoal com `repo` + `workflow`) se for `main`.
- O deploy real foi verificado pela URL pública, mas a RAM do Superset no plano Hobby deve ser acompanhada no painel.
- Projetos antigos vazios na conta Railway (`brilliant-possibility`, `renewed-forgiveness`) não foram tocados.
- Segurança: nenhuma senha ou chave foi escrita em arquivo versionado nem neste documento; a senha do `admin` fica só na variável `SUPERSET_ADMIN_PASSWORD` do serviço `superset`.
