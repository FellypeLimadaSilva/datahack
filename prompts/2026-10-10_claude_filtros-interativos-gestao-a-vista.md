# Sessão: filtros interativos, paleta e Visão geral de gestão à vista no Superset

- **Ferramenta:** Claude Code (Claude Sonnet 5.5), com 2 subagentes de pesquisa/desenho
- **Data:** 2026-10-10
- **Quem usou:** Mauricio Balboa
- **Fase:** 3 (dashboard final e plano de contingência)
- **Objetivo:** deixar o dashboard Superset (inclusive o Plano B, sem banco) mais interativo, trocar a paleta e a fonte, transformar a Visão geral num painel de gestão à vista e entender por que a aba B1 estava vazia
- **Resultado:** alterações em `superset/build_bundle.js`, `superset/superset_config.py` e `superset/docker/reimport.py`, mais README e dicionário do chat. A investigação do B1 foi só de leitura: nada foi carregado no warehouse.

## Contexto lido pela IA antes de responder

`superset/build_bundle.js`, `superset/superset_config.py`, `superset/docker/reimport.py`, `superset/README.md`,
`docs/referencias/artefacts.html` (guia de estilos), `chatbot/app/knowledge.py`, `config/sources.yml`,
`scripts/dh.ps1`, `src/datahack_ingest/cli.py`, as tabelas `gold.*`, `ops.*` e `gold.controle_atualizacao`
do warehouse e o código do Superset 4.1.2 dentro do container.

Os prompts abaixo estão **como foram escritos**, com a grafia original.

---

## Prompt 1

> seguinte, preciso melhoras os filtros agora, e deixar interativo, esta muito basico, o dashboard em si, por mais que seja um plano de contigencia, preciso destas alterações

**Resposta resumida da IA**

- Diagnóstico: cada aba mostrava só a Coorte; os outros 7 filtros ficavam "fora de escopo" e a Modalidade estava fixa dentro dos gráficos.
- Passou de 8 para **19 filtros nativos**, cada aba com os seus: Modalidade virou filtro (padrão Presencial), cascata Área → Curso e Rede/Área → Instituição, deslizantes (CPC contínuo, vagas por 100 jovens, jovens de 18 a 24 anos) e seletores novos (Faixa do CPC, Ano do Censo, Quartil, Licenciatura, Área do Enade, Faixa de oferta, Grau).
- Configurou o filtro cruzado por clique. Descobriu que o importador do Superset **não** traduz os ids de `chart_configuration`; o `reimport.py` passou a fazer essa tradução.
- Validou no navegador e no Plano B (planilhas, porta separada): os KPIs saíram idênticos aos do Postgres.

**O que foi aproveitado ou corrigido**

- Filtro cruzado: no Superset 4.1.2 só **tabela e tabela dinâmica** emitem clique. Barras simples e bolhas não. Uma tentativa de contornar com a mesma coluna no eixo e na série deu "Unexpected error" e foi desfeita. O texto de ajuda do dashboard foi corrigido duas vezes até ficar só com o que funciona.
- Funil por rede do P5 deixou de obedecer ao filtro de Rede (filtrar por rede o zerava).
- O build agora falha se um filtro apontar para coluna, aba ou filtro-pai inexistente.
- Os dados ao vivo estavam incompletos (coorte 2020, 2 anos de Censo, B1 vazio): os filtros de coorte, ano e município **não** foram testados com dados completos.

---

## Prompt 2

> daquele do artefatos, é so aquelas cores?

**Resposta resumida da IA**

- Interpretou "artefatos" como o guia de estilos `docs/referencias/artefacts.html`.
- Respondeu que o guia tem mais cores que as de gráfico: marca (azul e azul-marinho), status (verde, amarelo, laranja, vermelho, azul-petróleo e cinza, cada um com fundo e texto), categórica de 5 cores, sequencial azul e divergente.
- Explicou que o dashboard usava 8 cores categóricas, 3 delas de fora da lista de gráficos do guia.

**O que foi aproveitado ou corrigido:** só consulta. Serviu de base para o prompt seguinte.

---

## Prompt 3

> use outros cores do artefato, estas cores estao pessimas, e use a fonte ROBOT

**Resposta resumida da IA**

- Trocou o trio de resultado (concluíram verde, saíram laranja, em curso azul), tirou o rosa e o cinza e aplicou a fonte **Roboto** (interpretou "ROBOT" como Roboto).
- A Roboto é carregada do Google Fonts pelo CSS do dashboard; sem internet cai para Segoe UI. Embutir os arquivos da fonte (para funcionar offline) ficou como opção, pendente de autorização para baixá-los.

**O que foi aproveitado ou corrigido**

- A configuração de tema do Superset não mudou o texto da página; foi preciso uma regra de CSS com `!important`.
- O texto desenhado **dentro** dos gráficos (ECharts) continua sem Roboto no 4.1.2.
- Os números grandes (KPI) ignoram a cor configurada; a configuração morta foi removida.

---

## Prompt 4

> este amarelo diarreia esta pessima

**Resposta resumida da IA**

- Trocou o laranja de "saíram do curso" pelo vermelho do guia (`#DC3545`) e tirou amarelo, laranja, vermelho e verde da paleta das outras séries (que ficou em azul, roxo, azul-petróleo e cinza).
- Alertou que vermelho e verde são difíceis de distinguir para quem tem daltonismo.

**O que foi aproveitado ou corrigido:** a causa real só apareceu no prompt 5 (mapa de cores global por nome da série), então esta troca foi parcial.

---

## Prompt 5

> *(imagem de um painel de operações de recebimento: cabeçalho escuro, filtros em linha, cartões de KPI com variação, barras por status e tooltip rico)*
>
> eu preciso de uma gestao de vista, onde o usuario batera o olho e vera todas as informações necessarias, nao quero que o usuario navegue pela "visao geral" outras abas ele pode navegar, mas na geral nao pode, entao preciso disto, a paleta esta pessima ainda, use a cabeça, e pense mais, use agentes, se inspire neste modelo de dash da imagem

**Resposta resumida da IA**

- Usou **dois subagentes em paralelo**: um verificou no código do Superset 4.1.2 o que é possível (barra de filtros horizontal, modo tela cheia, cartões de KPI em HTML, cor por barra, altura, filtro cruzado, fonte); o outro desenhou paleta e layout.
- **Causa raiz das reprovações de cor** (achada pelo agente de desenho): o `label_colors` vale para o painel todo e casa pelo **nome** da série, então todo "Saíram do curso" ficava vermelho, até nos rankings.
- **Paleta nova, com regra:** magnitude em tons de uma matiz (cinza-azulado `#818AA6`); cor saturada só onde há julgamento (concluíram azul-marinho, em curso `#C6CAD7`, saíram `#B71C1C`). Sem rosa, amarelo nem laranja. Toda métrica começa neutra.
- **Visão geral reconstruída para uma tela (1920×1080, sem rolagem):** barra de filtros horizontal (Coorte e Modalidade), 6 cartões de KPI feitos com o gráfico Handlebars (concluíram, saíram com "≈ N de cada 10", em curso, ingressantes, evasão anual com variação sobre 2023, municípios sem curso presencial) e 6 gráficos com perguntas de gestão como título. Cabeçalho escuro, barra superior do Superset escondida por CSS.
- Mudanças de configuração: flag `HORIZONTAL_FILTER_BAR`, extensão da sanitização de HTML (style/class) e novo esquema de cores `univag`.
- Validou o painel no Plano B: cartões idênticos, sem erros.

**O que foi aproveitado ou corrigido**

- O relatório do agente de desenho propunha um bloco de "insights" em texto dinâmico; ficou de fora por falta de espaço vertical. A ideia de gráficos Handlebars para os insights não foi implementada.
- Corrigido ao longo do teste: título do cabeçalho ilegível (escuro sobre escuro), cartões cortados por causa do cabeçalho dos gráficos (escondido por CSS), números sem ponto de milhar (formatação em SQL portátil para Postgres e SQLite).
- Limites assumidos: altura em pixels (cabe até ~930 px de altura útil; notebook menor rola); não existe meta nos dados, então nada de verde/vermelho de "bom/ruim"; "Evasão 2024" e "Municípios sem oferta" aparecem como "—" enquanto faltarem os dados.
- Os dois subagentes só leram arquivos; as edições foram feitas pela sessão principal.

---

## Prompt 6

> *(captura da aba B1 · Desertos de ensino superior com "Metadados" nos cartões e filtros e "No results were returned for this query" nos gráficos)*
>
> por que esta aba esta desta maneira?

**Resposta resumida da IA**

- A tabela `gold.b1_desertos_municipio` tem **0 linhas**; não é erro do dashboard. "Metadados" é a tradução, no Superset em português, de "sem dado".
- A fonte `ibge_populacao_idade_mt` consta como `failed` em `gold.controle_atualizacao`, e o B1 depende dela e do Censo.

**O que foi aproveitado ou corrigido:** a causa completa só foi fechada no prompt 7.

---

## Prompt 7

> investigue

**Resposta resumida da IA**

- A pasta `data/landing/inep/` está vazia (as 4 fontes obrigatórias do INEP não têm arquivo), a Bronze tem 0 linhas e `ops.ingestion_runs` está sem execuções. A Gold atual é resto de uma construção com dados de teste, por isso só aparece a coorte 2020.
- O B1 precisa do Censo (vagas) e do IBGE (população); nenhum está carregado.
- A fonte do IBGE **funciona hoje**: carga em `--dry-run` extraiu 987 linhas (141 municípios × 7 idades). O `failed` antigo foi falha pontual.
- Caminho proposto: baixar os arquivos do INEP para Downloads, rodar `scripts\dh.ps1 import-downloads` e depois `scripts\dh.ps1 pipeline`.

**O que foi aproveitado ou corrigido**

- Só leitura e extração sem gravar. A execução do pipeline foi **deixada pendente**, porque substituiria a Gold usada pelo dashboard; a IA pediu confirmação e os arquivos do INEP, que não estavam em Downloads.
- Não foi encontrado erro registrado da carga do IBGE; a explicação de "falha pontual" é inferência.

---

## Prompt 8

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**Resposta resumida da IA:** este arquivo, mais uma linha no índice de `prompts/README.md`.
