# Sessão: de onde vêm os dados do dashboard e o `.env` é público?

- **Ferramenta:** Claude Code (Claude Sonnet 5.5)
- **Data:** 2026-10-10
- **Quem usou:** Mauricio Balboa
- **Fase:** 3 (repositório final e uso de IA)
- **Objetivo:** confirmar que o dashboard Superset lê o DW (schema `gold`) e que as credenciais não estão públicas
- **Resultado:** verificação apenas. Nenhum arquivo do pipeline, do dbt ou do dashboard foi alterado nesta sessão.

## O que a IA conferiu antes de responder

- `.gitignore` e `git ls-files` (quais `.env` são versionados) e `git log --all -- .env` (se o `.env` já entrou no histórico).
- `superset/up.ps1`, `superset/docker-compose.yml`, `superset/docker/reimport.py`, `superset/build_bundle.js` e `superset/README.md`
  (como o Superset se conecta ao warehouse).
- `docker ps` (quais containers estavam no ar) e os **nomes** das variáveis em `superset/.env`, sem ler os valores.
- `git remote -v` (repositório de origem).

---

## Prompt 1

> so me confirme uma coisa, os dados mostrados, estao sendo puxados do dw, a partir da .env que esta publica, correto?

**Resposta resumida da IA**

- **Dados vêm do DW: confirmado.** O Superset conecta em `warehouse:5432` com o papel `dh_bi_reader` (somente leitura,
  `search_path = gold`). Cada dataset é uma tabela `gold.*`. Os containers `rota-superset-superset-1` e
  `datahack-warehouse-1` estavam saudáveis. O `superset/.env` tem as variáveis `WAREHOUSE_*` e o compose não usa a
  variável do Plano B, então o modo é warehouse (não foi conferido visualmente no navegador).
- **`.env` público: corrigido.** O `.gitignore` bloqueia `.env` e `.env.*`; só o `.env.example` é versionado, com senhas
  `__GERAR__`. `git log --all -- .env` não retorna nenhum commit. O `superset/.env` também fica fora do Git. O pacote do
  dashboard leva só `placeholder` no lugar da senha, e `reimport.py` cria a conexão a cada subida a partir de
  `WAREHOUSE_BI_PASSWORD`.
- O que é público é o repositório `FellypeLimadaSilva/datahack` (se o repositório for público no GitHub, o que não foi
  checado): código e `.env.example`, sem credenciais. Quem clonar precisa subir o próprio warehouse e rodar o pipeline.
- Se o `.env` tiver aparecido em algum lugar público, as senhas devem ser trocadas.

**O que foi aproveitado ou corrigido:** a premissa "o `.env` está público" estava errada e foi corrigida com evidência
do repositório. A parte "dados vêm do DW" foi confirmada.

---

## Prompt 2

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**Resposta:** este arquivo, mais a linha no índice [prompts/README.md](README.md). Esta janela de contexto tem só os
dois prompts acima; as outras sessões já têm arquivo próprio nesta pasta.

---

## Pontos para defender na banca

- O dashboard lê só a camada Gold, por um papel somente leitura, sem acesso a bronze, silver ou ops.
- Nenhuma credencial está no repositório: `.env` ignorado, `.env.example` com placeholders, senha injetada na subida.
