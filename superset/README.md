# Rota do Diploma · Dashboard Apache Superset sobre a Gold

Dashboard de 9 abas (Visão geral, P1–P5, B1, B2, Fontes e metodologia), 54 gráficos e 19 filtros nativos (em cascata, com seletores e faixas deslizantes), lendo **direto o schema `gold` do warehouse** (o mesmo que o dbt publica e o Streamlit consome via `outputs/`). Segue o Guia de Estilos UNIVAG (fonte **Roboto**, carregada do Google Fonts pelo CSS do dashboard; sem internet cai para Segoe UI). Validado no Superset **4.1.2**.

```
INEP/IBGE ─▶ bronze ─▶ dbt (silver, gold_candidate) ─▶ portões ─▶ gold ─▶ Superset (papel dh_bi_reader, só leitura)
                                                                    └──▶ outputs/ ─▶ Streamlit
```

Nada de camada própria: cada dataset do Superset é uma tabela `gold.*` (`p1_trajetoria_coorte`, `p2_desistencia_curso`, `p2_desistencia_area`, `p3_rede_modalidade_ano`, `p4_*`, `p5_*`, `b1_desertos_municipio`, `b2_*`, `controle_atualizacao`). Quando o pipeline publica uma nova Gold (troca atômica de schema) ou faz `rollback`, o dashboard passa a mostrar a nova versão sem reimportar nada: a publicação refaz o `GRANT SELECT` ao `dh_bi_reader`.

## Subir (Windows, PowerShell)

Pré-requisito: o warehouse de pé e a Gold publicada.

```powershell
.\scripts\dh.ps1 up-lite
.\scripts\dh.ps1 pipeline
cd superset
powershell -ExecutionPolicy Bypass -File .\up.ps1
```

O `up.ps1` lê a senha do `dh_bi_reader` no `.env` da raiz (gerado por `dh.ps1 env`), grava um `superset/.env` (fora do Git) com uma chave e uma senha de `admin` aleatórias, sobe Superset + um Postgres só de metadados e imprime o endereço e a senha. Abra **http://localhost:8088**. A primeira abertura demora (o Superset sobe e importa o dashboard); depois cada tela responde em milissegundos.

Visitantes sem login conseguem **ler** (papel `Public` com acesso aos 13 datasets). Quem edita entra como `admin`.

Em Linux/macOS ou sem PowerShell: crie `superset/.env` com `SUPERSET_SECRET_KEY`, `SUPERSET_ADMIN_PASSWORD`, `WAREHOUSE_BI_PASSWORD`, `WAREHOUSE_NETWORK` (padrão `datahack_warehouse`) e `WAREHOUSE_DB`, e rode `docker compose up -d --build` nesta pasta.

## Visão geral = gestão à vista

Uma tela só (1920×1080, sem rolagem): 6 cartões de KPI (concluíram, saíram, em curso, ingressantes, evasão anual do Censo com variação, municípios sem curso presencial) e 6 gráficos, cada um com uma pergunta de gestão no título. Filtros em linha no topo (Coorte e Modalidade); as outras abas continuam rolando normalmente.

- **Cartões** são gráficos *Handlebars*: o SQL entrega o texto pronto (pt-BR, ponto de milhar, portátil para Postgres e SQLite) e o template só imprime. Precisam de `HTML_SANITIZATION_SCHEMA_EXTENSIONS` e da flag `HORIZONTAL_FILTER_BAR` no `superset_config.py` (reiniciar o Superset ao mudar).
- **Cores com regra:** magnitude em tons de navy (`#818AA6`), resultado da trajetória com cor própria (concluíram navy, em curso cinza-azulado, saíram vermelho `#B71C1C`), nada de rosa, amarelo ou laranja. O `label_colors` do dashboard vale para o painel todo e casa pelo **nome** da série, por isso toda métrica começa neutra e só o resultado da trajetória tem cor.
- **Tela cheia:** o CSS do dashboard esconde a barra superior do Superset. Em notebook pequeno (< 1080 px de altura útil) a Visão geral rola um pouco; use F11 ou zoom do navegador a 90%.
- Evasão anual e "municípios sem oferta" dependem de dados do Censo 2024 e do B1; sem eles o cartão mostra "—".

## Como o Superset chega ao warehouse

- O container entra na rede Docker do warehouse (`${COMPOSE_PROJECT_NAME}_warehouse`, padrão `datahack_warehouse`) e conecta em `warehouse:5432` com o papel **`dh_bi_reader`** (somente leitura, `search_path = gold`, timeout de 120 s). Não há acesso a bronze, silver ou ops.
- A senha **nunca vai no pacote nem no Git**: o `docker/reimport.py` cria/atualiza a conexão a cada subida, a partir de `WAREHOUSE_BI_PASSWORD`.

## Editar o dashboard

- **Pela interface:** edite à vontade como `admin`. Para guardar no repositório: dashboard › ⋯ › Exportar. Atenção: `reimport.py --force` **apaga e recria** a partir do `bundle/rota_do_diploma.zip`.
- **Pelo código:** edite `build_bundle.js` (métricas, gráficos, filtros, textos), rode `node build_bundle.js` e depois:

```powershell
docker compose exec -T superset python /app/reimport.py --force
```

O import padrão do Superset só sobrescreve o dashboard, **não** gráficos/datasets já existentes; por isso o `--force`. Os UUIDs são derivados dos nomes (determinístico).

## Plano B: o mesmo dashboard sem banco de dados (planilhas)

Se o Postgres cair, o dashboard inteiro (9 abas, 54 gráficos, filtros, chat) roda lendo **planilhas**: csv, tsv, xlsx, xlsm, xls, xlsb, ods, parquet, json, jsonl, e esses mesmos dentro de zip/gz. Só precisa do Docker.

```powershell
.\scripts\dh.ps1 planilhas                                  # sobe tudo no endereço de sempre
# ou, só o Superset:  cd superset; powershell -ExecutionPolicy Bypass -File .\up.ps1 -Planilhas
```

Solte os arquivos em `superset/planilhas/`: em ~10 s o painel recarrega sozinho. Com a pasta vazia ele usa as exportações da Gold que já estão em `outputs/`, ou seja, **sobe com os últimos números publicados sem você fazer nada**. Para voltar ao normal: `.\up.ps1` (os dois modos usam a mesma porta, um para o outro).

```
planilhas (qualquer formato) ─▶ docker/planilhas.py ─▶ SQLite (arquivo local, só leitura) ─▶ Superset ─▶ o mesmo dashboard
   superset/planilhas/  (vale primeiro)                                                        └──▶ chat com IA (mesmo arquivo)
   outputs/             (se a planilha não existir)
```

- **Mesmo painel, outra fonte.** `reimport.py` (com `DATA_SOURCE=planilhas`) aponta os 13 datasets para tabelas do SQLite e troca o aviso da aba "Fontes e metodologia" para "modo planilhas". Gráficos, métricas e filtros não mudam: o contrato de colunas (`bundle/contrato_planilhas.json`, documentado em `planilhas/CONTRATO.md`) sai do mesmo `build_bundle.js` dos datasets.
- **Reconhece sozinho** qual planilha é qual tabela (pelo nome do arquivo/aba ou pelas colunas), acha o cabeçalho mesmo com títulos acima, aceita vírgula decimal, `;`, cp1252, `%`, `R$`, `sim/não`, e abas/arquivos extras são ignorados. Detalhes e limites: [`planilhas/LEIA-ME.md`](planilhas/LEIA-ME.md).
- **Seguro.** O SQLite é aberto só para leitura (`mode=ro`); a troca do arquivo é atômica (se a nova carga falhar, a anterior continua); arquivo corrompido vira um aviso no relatório, não uma queda.
- **Conferir o que foi lido:** `docker compose -f docker-compose.planilhas.yml exec superset python /app/planilhas.py --check`.
- **Prova de equivalência.** As 53 consultas do dashboard rodadas no Postgres e no SQLite devolveram os mesmos números (48 idênticas, 5 só com outra ordem entre empates, 0 erros). O teste de formatos (`tests/test_planilhas.py`) grava 11 tabelas em xlsx, ods, xls, csv cp1252, parquet, json, jsonl, tsv.gz e zip e confere cada uma contra a Gold.

O que o Plano B **não** faz: não recalcula nada. As taxas, o corte de células pequenas e os rankings vêm prontos da Gold; se a planilha for montada à mão, essas regras ficam por conta de quem montou.

Teste dos formatos (dentro da imagem, sem subir o Superset):

```powershell
docker run --rm --entrypoint sh -v "${PWD}/docker/planilhas.py:/app/planilhas.py:ro" -v "${PWD}/bundle:/bundle:ro" -v "${PWD}/tests:/tests:ro" -v "${PWD}/../outputs:/outputs:ro" rota-superset-planilhas-superset -c "pip install --user -q xlwt==1.3.0; python /tests/test_planilhas.py"
```

## Pitch fora da máquina da equipe

O guia exige que o dashboard funcione sem o banco local. O Streamlit lê `outputs/`. O Superset precisa de servidor: o caminho mais simples é **levar o notebook da equipe** com `warehouse` e `up.ps1` de pé (o guia permite notebook próprio; teste o HDMI). Sem o banco, o **Plano B acima** sobe o mesmo dashboard só com o Docker e as planilhas. Leve também o **plano C** (PDF com prints de cada aba ou vídeo de 1–2 min): sem ele, −3 pontos.

## Decisões de modelagem que valem no pitch

- **Taxa ponderada.** A Gold já entrega taxas em %. Ao reagregar (filtros que juntam linhas) o painel pondera pelos ingressantes: `SUM(taxa × ingressantes) / SUM(ingressantes)`. Nunca média simples de taxas.
- **Células pequenas.** A regra (< 10 alunos) é aplicada pelo dbt: o painel só vê o que já foi mascarado. Rankings só com 30+ ingressantes (`is_elegivel_ranking`).
- **Cor presa à entidade.** Concluíram azul, Saíram rosa, Em curso cinza, em todos os gráficos (paleta UNIVAG).
- **Filtros nativos casam por nome de coluna** entre datasets, e cada aba mostra só os que valem para ela (o resto fica em "fora de escopo"): Visão geral/P1/P2 → Coorte e Modalidade (padrão Presencial; limpe para somar EAD); P2 → Ano do curso, Rede, Grau, Área, Curso (rótulo) e Instituição; P3 → Rede, Modalidade e Ano do Censo; P4 → Rede, Modalidade, Grau, Área, Instituição, Faixa do CPC e **CPC contínuo (deslizante)**; P5 → Rede, Modalidade, Área, Instituição, Licenciatura e Área do Enade; B1 → Município, Faixa de oferta e dois deslizantes (vagas por 100 jovens, jovens 18–24); B2 → Modalidade, Ano do Censo e Quartil. Área → Curso e Área/Rede → Instituição são **em cascata** (as opções encolhem conforme o filtro pai). Matrizes que comparam coortes são excluídas do filtro de coorte de propósito, e o funil por rede do P5 não obedece ao filtro de Rede (ele já compara as redes). A lista fica no array `FILTERS` do `build_bundle.js`, que valida colunas, abas e pais no build.
- **Filtro cruzado.** Clicar numa linha de **tabela** ou **tabela dinâmica** filtra os outros gráficos da mesma aba (clique de novo para limpar; o filtro ativo aparece no topo da barra lateral). Barras sem série e bolhas **não** emitem filtro no Superset 4.1.2; para elas valem os filtros da barra e o botão direito (*Detalhar por*, *Ver registros*). O importador do Superset não traduz os ids de `chart_configuration`; o `reimport.py` faz isso após o import.
- **Evasão anual (Censo) e desistência acumulada (Trajetória) nunca no mesmo gráfico.**

## Estrutura

| Arquivo | Para quê |
|---|---|
| `build_bundle.js` | Gera `bundle/rota_do_diploma.zip` (13 datasets sobre a Gold, métricas, 54 gráficos, filtros, layout) |
| `bundle/rota_do_diploma.zip` | O pacote de importação (a pasta desempacotada fica fora do Git) |
| `docker-compose.yml`, `Dockerfile` | Superset + Postgres de metadados, na rede do warehouse |
| `docker-compose.planilhas.yml` | **Plano B**: Superset sozinho (metadados em SQLite), lendo planilhas; sem warehouse e sem rede externa |
| `up.ps1` | Gera `superset/.env` a partir do `.env` da raiz e sobe tudo; `-Planilhas` sobe o Plano B |
| `docker/init.sh`, `docker/reimport.py` | Boot, conexão com a fonte (warehouse ou planilhas), (re)importação e acesso público |
| `docker/planilhas.py` | Carregador do Plano B: planilhas de qualquer formato → SQLite (`--check`, `--watch`, `--modelo`) |
| `planilhas/` | Onde soltar as planilhas (conteúdo fora do Git); `LEIA-ME.md` e `CONTRATO.md` explicam |
| `tests/test_planilhas.py` | Prova que cada formato vira os mesmos dados da Gold |
| `superset_config.py` | pt-BR, paleta UNIVAG, acesso anônimo de leitura, formato numérico `1.234,5` |

## Problemas comuns

- *"Waiting on Warehouse · gold" por muito tempo:* confira se a Gold existe (`dh.ps1 pipeline`) e se a rede `datahack_warehouse` está de pé (`docker network ls`).
- *Falha ao conectar:* `docker compose logs superset`; a senha do `dh_bi_reader` no `superset/.env` precisa ser a do `.env` da raiz. Rode `up.ps1` de novo para sincronizar.
- *Gráfico vazio no P5 ou B1:* a fonte correspondente (Enade 2025, IBGE 9514) ainda não foi carregada; veja `controle_atualizacao` na aba "Fontes e metodologia".

## Chat com IA (opcional)

`chat/tail_js_custom_extra.html` é montado em `/app/superset/templates/` e mostra o botão **"Pergunte aos dados"** só nas
páginas de dashboard; ele abre o serviço `../chatbot` (porta 8099) num iframe e informa a aba ativa e os filtros.
Sem o serviço no ar o botão aparece, mas o painel fica vazio. Detalhes e como subir: `chatbot/README.md`.
Cuidado ao editar o arquivo: o Jinja do Superset lê o conteúdo, então evite `{#`, `{{` e `{%` no JS/CSS.
