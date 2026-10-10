# Sessão: onde hospedar o front e o back (Vercel × Railway)

- **Ferramenta:** Claude Code (Claude Sonnet 5.5)
- **Data:** 2026-10-10
- **Quem usou:** Mauricio Balboa
- **Fase:** Contingência (plano B)
- **Objetivo:** decidir onde hospedar o sistema, se o front pode ir para a Vercel e se o back também ou se precisa da Railway
- **Resultado:** análise apenas. Nenhum arquivo do projeto foi alterado nesta sessão. Decisão: tudo na Railway; a Vercel só entra se houver uma página-casca com iframe.

## Contexto lido pela IA antes de responder

`chatbot/` (Dockerfile, `requirements.txt`, README), `gateway/` (nginx), `superset/superset_config.py`
e `superset/docker-compose.planilhas.yml`.

---

## Prompt 1

> quero hospedar meu front na vercel, o backend consigo hospedar na vercel tambem? ou preciso usar a railway para o back?

**Resposta resumida da IA**

- A Vercel roda funções serverless (sem estado, de curta duração). O conjunto do projeto não cabe nesse modelo:
  - **Superset:** aplicação grande e permanente, com metadados e Docker. Não roda na Vercel.
  - **Warehouse (Postgres):** precisa de um banco que o projeto controle. A Vercel não hospeda isso.
  - **Chatbot (FastAPI):** a chave da DeepSeek fica em volume (`chatbot-data`) e o limite de taxa do `slowapi`
    usa memória do processo. Em serverless o disco some a cada execução e a memória não é compartilhada.
  - **Gateway (nginx):** só junta os serviços num endereço; na Vercel esse papel seria de rewrites.
- Recomendação: Vercel para o front, Railway para banco, chatbot e Superset (a Railway roda contêineres, então
  os `docker-compose` viram serviços quase sem mudança).
- Ressalva: no repositório o front de fato é o próprio Superset (dashboard + widget do chat), então a pergunta
  de volta foi se existia um front separado.

**O que foi aproveitado ou corrigido:** nada foi implementado. A resposta serviu para descobrir que a pergunta
real era outra (ver o Prompt 2).

---

## Prompt 2

> é o superset, este sistema é o plano de contigencia, entao vai ser o superset tudo embedado

**Resposta resumida da IA**

- Sem front separado, não há o que hospedar na Vercel: **tudo vai para a Railway**.
- O plano B (`docker-compose.planilhas.yml`) é um contêiner só (Superset com SQLite e planilhas, sem banco e
  sem rede externa). Na Railway fica um serviço, com volume persistente em `/app/superset_home`.
- A Vercel só serve para uma página HTML opcional com o dashboard num `<iframe>` (domínio próprio, contexto).
- Ajustes necessários no `superset_config.py` para embutir em outro domínio:
  1. `TALISMAN_ENABLED = False` já remove o `X-Frame-Options` (ponto já resolvido).
  2. Cookies entre domínios: `SESSION_COOKIE_SAMESITE = "None"` e `SESSION_COOKIE_SECURE = True`, ou
     subdomínios do mesmo domínio.
  3. Acesso sem login: `PUBLIC_ROLE_LIKE = "Gamma"` já existe, mais permissão do dashboard para o papel Public.
     O caminho completo seria o Embedded SDK com guest token, que exige um backend para gerar o token.
  4. `SUPERSET_SECRET_KEY` e `SUPERSET_ADMIN_PASSWORD` como variáveis da Railway, nunca no repositório.
  5. Porta: o Superset escuta na 8088 e a Railway usa a variável `PORT`.
- Atenções: volume obrigatório (senão o SQLite some a cada deploy), 1 a 2 GB de RAM, e planilhas embutidas na
  imagem com `COPY` em vez de volume do compose.

**O que foi aproveitado ou corrigido:** nada foi implementado. Ficou como proposta: ajustar Dockerfile e
`superset_config.py`, criar `railway.json` e, se desejado, a página de iframe para a Vercel.

---

## Prompt 3

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**Resposta resumida da IA**

- Gerou este arquivo no formato da pasta `prompts/` (nome padrão, cabeçalho, um bloco por prompt) e
  acrescentou a linha correspondente ao índice em [`README.md`](README.md).

**O que foi aproveitado ou corrigido:** este próprio documento.
