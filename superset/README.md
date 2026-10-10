# Rota do Diploma · Dashboard Apache Superset sobre a Gold

Dashboard de 9 abas (Visão geral, P1–P5, B1, B2, Fontes e metodologia), 54 gráficos e 8 filtros nativos, lendo **direto o schema `gold` do warehouse** (o mesmo que o dbt publica e o Streamlit consome via `outputs/`). Segue o Guia de Estilos UNIVAG. Validado no Superset **4.1.2**.

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

## Pitch fora da máquina da equipe

O guia exige que o dashboard funcione sem o banco local. O Streamlit lê `outputs/`. O Superset precisa de servidor: o caminho mais simples é **levar o notebook da equipe** com `warehouse` e `up.ps1` de pé (o guia permite notebook próprio; teste o HDMI). Leve o **plano B** (PDF com prints de cada aba ou vídeo de 1–2 min) de qualquer forma: sem ele, −3 pontos.

## Decisões de modelagem que valem no pitch

- **Taxa ponderada.** A Gold já entrega taxas em %. Ao reagregar (filtros que juntam linhas) o painel pondera pelos ingressantes: `SUM(taxa × ingressantes) / SUM(ingressantes)`. Nunca média simples de taxas.
- **Células pequenas.** A regra (< 10 alunos) é aplicada pelo dbt: o painel só vê o que já foi mascarado. Rankings só com 30+ ingressantes (`is_elegivel_ranking`).
- **Cor presa à entidade.** Concluíram azul, Saíram rosa, Em curso cinza, em todos os gráficos (paleta UNIVAG).
- **Filtros nativos casam por nome de coluna** entre datasets, e cada um tem escopo por aba (Coorte: Visão geral, P1, P2; Ano do curso: só as áreas do P2; Rede/Modalidade/Área/Instituição onde a Gold tem a coluna; Município: B1). Matrizes que comparam coortes são excluídas do filtro de coorte de propósito.
- **Evasão anual (Censo) e desistência acumulada (Trajetória) nunca no mesmo gráfico.**

## Estrutura

| Arquivo | Para quê |
|---|---|
| `build_bundle.js` | Gera `bundle/rota_do_diploma.zip` (13 datasets sobre a Gold, métricas, 54 gráficos, filtros, layout) |
| `bundle/rota_do_diploma.zip` | O pacote de importação (a pasta desempacotada fica fora do Git) |
| `docker-compose.yml`, `Dockerfile` | Superset + Postgres de metadados, na rede do warehouse |
| `up.ps1` | Gera `superset/.env` a partir do `.env` da raiz e sobe tudo |
| `docker/init.sh`, `docker/reimport.py` | Boot, conexão com o warehouse, (re)importação e acesso público |
| `superset_config.py` | pt-BR, paleta UNIVAG, acesso anônimo de leitura, formato numérico `1.234,5` |

## Problemas comuns

- *"Waiting on Warehouse · gold" por muito tempo:* confira se a Gold existe (`dh.ps1 pipeline`) e se a rede `datahack_warehouse` está de pé (`docker network ls`).
- *Falha ao conectar:* `docker compose logs superset`; a senha do `dh_bi_reader` no `superset/.env` precisa ser a do `.env` da raiz. Rode `up.ps1` de novo para sincronizar.
- *Gráfico vazio no P5 ou B1:* a fonte correspondente (Enade 2025, IBGE 9514) ainda não foi carregada; veja `controle_atualizacao` na aba "Fontes e metodologia".
