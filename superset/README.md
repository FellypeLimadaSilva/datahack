# Rota do Diploma · Dashboard Apache Superset

Dashboard de 9 abas (Visão geral, P1–P5, B1, B2, Fontes e metodologia), 50 gráficos, 10 filtros nativos, texto de método em cada gráfico. Segue o Guia de Estilos UNIVAG. Validado no Superset **4.1.2** (importação limpa, 0 erros de consulta, todos os gráficos renderizando).

```
Superset (8088)  ──lê──▶  Postgres (5434) schema "mart"  ◀──carrega──  seu pipeline (staging → mart)
   dashboard                 6 tabelas + 1 view                          sql/10_marts_from_staging.sql
```

O Superset **só lê o schema `mart`**. O pipeline da equipe termina de popular as tabelas do contrato (`sql/00_marts_ddl.sql`). O dashboard não conhece os dados brutos.

## Subir (precisa do Docker Desktop aberto)

Com dados **sintéticos de demonstração** (para ver tudo funcionando já):

```bash
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

Sem dados (marts vazios, esperando o pipeline):

```bash
docker compose up -d --build
```

Abra **http://localhost:8088** (usuário `admin`, senha `admin`). O dashboard é importado sozinho no primeiro boot. A primeira abertura demora ~20–30 s (o Superset sobe e o Postgres esquenta). Link do dashboard: `http://localhost:8088/superset/dashboard/rota-do-diploma/`.

Visitantes sem login conseguem **ler** (`PUBLIC_ROLE_LIKE = "Gamma"`). Troque a senha do `admin` e a `SUPERSET_SECRET_KEY` se for expor na internet.

## Trocar os dados sintéticos pelos reais

1. O pipeline da equipe carrega os brutos em tabelas `stg.*` no Postgres `rota` (porta 5434, usuário/senha `rota`). Os nomes de colunas esperados estão no cabeçalho de `sql/10_marts_from_staging.sql`. Códigos como **texto**.
2. Rode a transformação (idempotente, pode repetir):

```bash
docker compose exec -T db psql -U rota -d rota -v ON_ERROR_STOP=1 -f - < sql/10_marts_from_staging.sql
```

3. Confira `mart.qualidade_checks` (aparece na aba "Fontes e metodologia"). **Antes de confiar nos números**, valide os 6 pontos do fim de `../docs/ANALISE_ROTA_DO_DIPLOMA.md` (escala das taxas TDA/TCA/TAP, "desistência inclui transferência?", etc.).
4. Gere o pacote **sem** a faixa "dados demonstrativos" e reimporte:

```bash
node build_bundle.js
docker compose exec -T superset python /app/reimport.py --force
```

## Extração para o repositório (regra do pitch fora da máquina)

```bash
sh export_outputs.sh
```

Grava `outputs/superset/mart_*.csv` (agregados, bem abaixo de 100 MB; vão para o Git). Em qualquer máquina com Docker:

```bash
docker compose up -d --build && sh load_outputs.sh
```

## Editar o dashboard

- **Pela interface**: edite à vontade. Para guardar a mudança no repositório: dashboard › ⋯ › Exportar. Mas atenção: `reimport.py --force` **apaga e recria** a partir do `rota_do_diploma.zip`.
- **Pelo código**: edite `build_bundle.js` (gráficos, métricas, filtros, textos) e rode `node build_bundle.js` + `reimport.py --force`. Os UUIDs são derivados dos nomes, então é determinístico.
- O import padrão do Superset só sobrescreve o dashboard, **não** os gráficos/datasets existentes. Por isso o `--force`.

## Para a nuvem (pitch em outra sala)

```bash
ROTA_DB_URI="postgresql+psycopg2://USUARIO:SENHA@HOST:5432/BANCO" node build_bundle.js
```

Suba o container `superset` em uma VM (ou use Preset) e o Postgres em Neon/Supabase; rode `sql/00_marts_ddl.sql` e `sh load_outputs.sh` adaptado ao host. Teste na rede do evento. **Leve o plano B** (PDF/vídeo) mesmo assim.

## Estrutura

| Arquivo | Para quê |
|---|---|
| `sql/00_marts_ddl.sql` | Contrato: tabelas `mart.*` (grão, chaves, colunas) |
| `sql/10_marts_from_staging.sql` | staging → mart (idempotente, com checagens) |
| `sql/90_demo_seed.sql` | Dados sintéticos (só demonstração) |
| `build_bundle.js` | Gera `bundle/rota_do_diploma.zip` (datasets, métricas, 50 gráficos, filtros, layout) |
| `docker/init.sh`, `docker/reimport.py` | Boot e (re)importação |
| `superset_config.py` | pt-BR, paleta UNIVAG, acesso público, formato numérico `1.234,5` |
| `export_outputs.sh`, `load_outputs.sh` | Marts ↔ `outputs/superset/*.csv` |

## Decisões de modelagem que valem no pitch

- **Taxa ponderada**: cada `mart` guarda alunos estimados (`n_* = taxa × ingressantes`); a métrica é `SUM(n_*) / SUM(ingressantes)`. Nunca média de taxas.
- **Célula pequena < 10**: suprimida por `HAVING` em cada gráfico (a regra mora na consulta, não na tela).
- **Cor presa à entidade**: Concluíram azul, Saíram rosa, Em curso cinza, em todos os gráficos.
- **Filtros nativos casam por nome de coluna** entre datasets; por isso `cpc_curso` usa `coorte_cpc` (se fosse `coorte`, o filtro de coorte zeraria o gráfico de CPC).
- **Evasão anual (Censo)** e **desistência acumulada (Trajetória)** nunca aparecem no mesmo gráfico.

## Problemas comuns

- *"Waiting on Rota do Diploma (mart)"* por muito tempo: o Postgres ainda esquentando; aguarde ou recarregue.
- *Importação falhou no boot*: `docker compose logs superset`; rode `reimport.py --force` para ver a mensagem.
- *Alterei o DDL e nada mudou*: o init do Postgres só roda na criação do volume. `docker compose down -v` apaga tudo (inclusive dados carregados).
