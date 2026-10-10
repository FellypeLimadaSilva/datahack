# Sessão Claude: análise do protótipo e dashboard Superset sobre a Gold

| | |
|---|---|
| **Data** | 2026-10-10 (dia do desenvolvimento) |
| **Ferramenta** | Claude Code (Claude Sonnet 5.5), app desktop, no Windows 11 |
| **Quem usou** | Mauricio |
| **Fase** | Fases 2 e 3 (protótipo e produto final) |
| **Escopo deste arquivo** | Somente os prompts **desta janela de contexto** (6 mensagens). Outras sessões do projeto (chat com IA, plano B em planilhas, filtros interativos, hospedagem) têm arquivos próprios nesta pasta e não estão aqui. |

## Resumo

Partindo de dois arquivos (`Rota do Diploma.html`, um protótipo, e `artefacts.html`, o guia do desafio), a sessão: (1) comparou o protótipo com o guia e com os dicionários do INEP e produziu um dashboard Apache Superset; (2) trouxe o repositório do GitHub, descobriu que ele já tinha uma plataforma ELT completa e subiu o trabalho para uma branch `develop`; (3) refez o dashboard para ler direto o schema `gold` do warehouse; (4) conferiu a sincronização com o GitHub; (5) parou tudo o que rodava localmente; (6) documentou os prompts (este arquivo).

Resultado no GitHub (`develop`): commits `fd4a223` (kit Superset inicial + análise) e `57bb123` (dashboard sobre a Gold).

---

## Prompt 1

> seguinte paizao, preciso que voce leia este artefacts, analise cada detalhe, e veja onde podemos mudar a rota do diploma.html, preciso do dash superset

**Contexto:** a pasta tinha só `Rota do Diploma.html` e `artefacts.html`.

**O que foi feito**
- Os dois HTML eram *bundles* (conteúdo comprimido em base64). Foram desempacotados com Node (não há Python na máquina) para ler o código real: o protótipo é um app React com **dados sintéticos** (gerados por hash), e o `artefacts.html` é o *Guia do participante* do DataHack UNIVAG 2026, com perguntas P1–P5, bônus B1–B2, rubricas, penalidades, dicionários de dados e os tokens do Guia de Estilos UNIVAG.
- Comparação protótipo × guia × bases do INEP. Divergências principais:
  - **P5**: o protótipo usava 4 níveis de proficiência que não existem na base (o Enade 2025 só traz o % no Padrão 1).
  - **B2**: "evasão com × sem FIES" é impossível com dados agregados por curso.
  - **P3**: fórmula da evasão anual com transferidos no numerador; faltavam privada com/sem fins lucrativos e a leitura de ano atípico.
  - **P2/P4**: faltavam áreas, ranking de menor desistência, coorte 2020, relação CPC × desistência e controles.
  - Paleta e tipografia diferentes do Guia de Estilos UNIVAG.
- Construído o kit `superset/` (Docker: Superset 4.1.2 + Postgres), com camada analítica `mart.*`, SQL de transformação idempotente, seed sintético só para demonstração e um gerador (`build_bundle.js`) do pacote de importação do dashboard (9 abas, 50 gráficos, 10 filtros).
- Validação de verdade: Docker subido, dashboard importado, todas as consultas conferidas e as telas inspecionadas no navegador embutido.

**Entregas:** `ANALISE_ROTA_DO_DIPLOMA.md` (hoje em `docs/`), pasta `superset/`, memórias do projeto.

**Correções e achados durante a execução (erros da IA e do ambiente)**
- Regex e *heredoc* gerando arquivos truncados/incorretos: refeitos com a ferramenta de escrita de arquivos.
- A imagem do Superset não trazia `psycopg2`: adicionado no `Dockerfile`.
- O esquema de importação do Superset é estrito (`impersonate_user` rejeitado).
- Descoberta: **a reimportação só sobrescreve o dashboard, não gráficos nem datasets existentes** → criado `reimport.py --force`.
- Filtros nativos casam por **nome de coluna** entre datasets: `cpc_curso.coorte` zerava o gráfico de CPC → coluna renomeada para `coorte_cpc`.
- Cor de série é chaveada pelo *nome da métrica*, não pelo rótulo → métricas renomeadas para "Concluíram", "Saíram do curso", "Em curso".
- Rankings horizontais saíam invertidos; gráfico de quadrantes do P5 quebrava (mesma coluna como entidade e série); formato numérico pt-BR só valia após reiniciar.
- Acesso anônimo dava redirecionamento ao login: o papel `Public` precisou de `datasource_access` nos datasets.

---

## Prompt 2

> https://github.com/FellypeLimadaSilva/datahack.git faça um pull desta pasta, analise tudo que tem, se tem algo novo, e faça uma nova branch "develop" e suba tudo que tem neste codigo nosso para lá

**O que foi feito**
- Clone numa pasta temporária para analisar sem misturar. O repositório já tinha uma **plataforma ELT completa**: PostgreSQL com bronze/silver/gold, dbt (82 testes), ingestão em Python, Airflow opcional, portões de qualidade, publicação atômica da Gold, `outputs/` e um dashboard Streamlit.
- Descoberto que a pasta de trabalho **já era** um clone, mas atrasado (5 commits). Feito `git pull --ff-only` na `main`, criada a `develop` e enviado o código.
- Adaptações para conviver com o repositório: `.gitignore` do repo ignorava `dist/` e `*.csv` → pasta do pacote virou `bundle/`; a porta 5433 já era do `warehouse` → Postgres do kit mudou para 5434; análise e protótipos foram para `docs/`.

**Incidente:** ao limpar CSVs de teste, um `rm -rf outputs` apagou o `outputs/.gitkeep` rastreado pelo Git. Percebido na hora e **restaurado com `git restore`**; nada mais foi afetado.

**Resultado:** `develop` criada no GitHub com o commit `fd4a223` (19 arquivos).

---

## Prompt 3

> aponte para warehouse do schema gold e faça

**O que foi feito**
- Estudo da Gold: `_gold__models.yml`, colunas das tabelas, escalas (`pct_proficiente` em 0–100), macros de supressão e como a publicação refaz o `GRANT SELECT` ao `dh_bi_reader` após a troca de schema.
- **Warehouse de teste isolado** (projeto compose `dhtest`, porta própria, senhas descartáveis) para não tocar no stack real do time; tabelas Gold carregadas dos CSVs de `outputs/`.
- Dashboard refeito sobre as 13 tabelas `gold.*`: 54 gráficos, 8 filtros com escopo por aba. Taxas reagregadas por **média ponderada** dos ingressantes (nunca média simples). A camada `mart.*`, o seed e os scripts de export foram removidos.
- Conexão criada no boot pelo `reimport.py` a partir de variáveis de ambiente: **a senha não vai no pacote nem no Git**. `up.ps1` gera o `superset/.env` com segredos aleatórios.
- Validação: login anônimo, 53 consultas com status 200 e linhas, números conferidos com o README do time (coorte 2020: 21,7 / 56,5 / 21,7 e 28.985 ingressantes).

**Achados que exigem decisão do time** (registrados em `docs/ANALISE_ROTA_DO_DIPLOMA.md`, §5)
1. Evasão anual (P3): o denominador do dbt inclui trancadas e falecidos; o guia, não. O painel mostra a fórmula do guia como principal e a da Gold ao lado.
2. P3 só separa Pública/Privada; faltam as categorias com e sem fins lucrativos.
3. B1: o dbt declara 141 municípios; o protótipo dizia 142 (conferir no IBGE).
4. `outputs/` do repositório é parcial (só coorte 2020, Censo 2021 e 2023, B1 vazio, sem Enade).

**Correções durante a execução**
- *Heredoc* truncou um arquivo grande de novo → passou a usar a ferramenta de escrita.
- Nomes de métrica com `%` e parênteses são arriscados como alias SQL → nomes simplificados (rótulos de exibição mantidos).
- Colunas vazias no CSV de preview foram tipadas como texto no banco de teste e quebravam somas (artefato do teste, não da Gold).
- Bug real: o ranking "menor desistência" repetia os mesmos cursos do "maior" (o SQL ordenava decrescente antes do `LIMIT`) → `order_desc` passou a seguir o sentido do ranking.
- O `up.ps1` imprimia sucesso mesmo quando o `docker compose` falhava → passou a abortar.

**Resultado:** commit `57bb123` na `develop`.

---

## Prompt 4

> suba as atualizações para a develop

**O que foi feito:** conferido `git status` e `fetch`. A `develop` local e a remota já estavam iguais (`57bb123`) e a árvore de trabalho estava limpa. **Nada novo a enviar**; foi informado ao usuário em vez de criar um commit vazio.

---

## Prompt 5

> e para de rodar localmente

**O que foi feito:** `docker compose down -v` no Superset e no warehouse de teste `dhtest` (containers, volumes e redes removidos, incluindo os dados fictícios do Enade/B1 usados só no teste) e remoção do `superset/.env` de teste (estava fora do Git). Conferido que não restou container, volume nem rede do projeto. O Docker Desktop foi deixado aberto, pois não foi iniciado por pedido do usuário; ficou a orientação de fechá-lo pela bandeja.

---

## Prompt 6

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**O que foi feito:** este arquivo, seguindo a convenção da pasta (`AAAA-MM-DD_HHMM_ferramenta_tema.md`) e acrescentando uma linha ao índice `prompts/README.md`.

---

## Conceitos de engenharia de dados discutidos e aplicados

- **Grão e chaves**: cada tabela Gold tem grão declarado (ex.: curso × coorte; ano × rede × modalidade); filtros nativos casam por nome de coluna entre datasets.
- **Média ponderada × média simples** de taxas; reagregação correta com `SUM(taxa × peso) / SUM(peso)`.
- **Anual × acumulado**: evasão anual (Censo) e desistência de coorte (Trajetória) nunca no mesmo gráfico.
- **Camadas e idempotência**: bronze → silver → gold; publicação atômica por troca de schema e `GRANT` refeito a cada publicação.
- **Privilégio mínimo**: Superset lê só `gold`, com o papel `dh_bi_reader`; senha fora do Git e do pacote.
- **Células pequenas (< 10)**: regra no dbt; rankings só com 30+ ingressantes.
- **Associação, não causa**: avisos por aba e nas descrições dos gráficos.
- **Reprodutibilidade**: UUIDs determinísticos no pacote, boot do zero validado, reimportação segura (`--force`).

## O que foi aproveitado e o que foi corrigido (para a rubrica de IA)

- **Aproveitado:** análise protótipo × guia; arquitetura do kit Superset; leitura da Gold; verificação dos números contra o README do time.
- **Corrigido ao conferir a saída da IA:** erros listados nos prompts 1 e 3 (arquivos truncados, importação que não sobrescreve gráficos, colisão de filtros por nome de coluna, ordenação de ranking, acesso anônimo). Cada um foi detectado por teste real (importação, consultas e inspeção das telas), não por suposição.
- **Limite honesto:** o dashboard foi validado contra um warehouse de teste com o *preview* de `outputs/` (coorte 2020, Censo 2021 e 2023). As partes de P5 (Enade) e B1 foram exercitadas com valores fictícios só no teste e **não** refletem dados reais.
