# Estratégia de ingestão e transformação (Fase 1)

Pergunta central: de cada 100 que entram numa graduação em Mato Grosso, quantos chegam ao diploma,
e em quais cursos a rota se perde?

## 1. Stack e justificativa

| Escolha | Por quê | Alternativa considerada |
|---|---|---|
| PostgreSQL 16 (Docker) | Aguenta o Censo 2024 (~450 MB de CSV, 2–3x em disco) com folga; cast seguro (`pg_input_is_valid`) que não derruba a carga; transação por arquivo garante idempotência; roles separam ingestão, transformação e leitura | DuckDB: mais simples e rápido para análise local, mas sem controle de acesso por camada e sem concorrência de escrita |
| Python (`datahack-ingest`) | Ingestão por código, lendo xlsx/CSV/zip em streaming, com manifesto de arquivos | pandas solto em notebook: não é idempotente nem auditável |
| ELT com recorte na extração | Dado fiel na Bronze e regras no dbt; só o filtro de UF antes de gravar (seção 2) | ETL completo: regra escondida no código de carga, sem teste nem linhagem |
| dbt | Transformações versionadas, testes de qualidade como gate, documentação gerada | SQL solto: sem testes nem linhagem |
| Dashboard lendo `outputs/` | Abre no pitch sem acesso ao banco (Caminho 1) | Conectar direto no banco: falha fora do laboratório |

## 2. Decisão: ELT, com recorte de escopo na extração

A arquitetura é **ELT medalhão**: o dado é carregado fiel ao arquivo na Bronze e toda regra
(tipos, chaves, junções, indicadores) fica no dbt, versionada e testada. A única transformação antes
de gravar é o **recorte de Mato Grosso** nos dois arquivos nacionais grandes, um filtro declarativo de
linhas que não altera nenhum valor.

Medido nos arquivos reais (Censo 2021 + 2023 e Trajetória coorte 2020):

| | Brasil inteiro | Só MT | Ganho |
|---|---|---|---|
| Censo cursos, 2 anos | 1.116.396 linhas · 973 MB · 110 s | 29.300 linhas · 26 MB · 48 s | 37x menos disco, 2,3x mais rápido |
| Trajetória, 1 coorte | 174.240 linhas · 82 MB · 35 s | 3.105 linhas · 1,8 MB · 32 s | 46x menos disco |
| Silver + Gold + 39 testes (dbt) | — | 15 s | |

Por quê: o desafio é sobre MT; o Brasil inteiro (4 anos de Censo + 6 coortes) passaria de 3 GB e
10+ minutos por carga nas máquinas do laboratório, sem uso nas perguntas. Ficam nacionais (pequenos):
Censo IES, CPC e IGC, úteis para comparar MT com o Brasil. Para voltar ao nacional, basta remover
o `filter` da fonte em `config/sources.yml` e recarregar.

Primeiros números (coorte 2020, MT, presencial, até 2024): 621 cursos, 28.985 ingressantes,
21,7% concluíram e 56,5% desistiram. Junção Trajetória ↔ Censo por código do curso: 99,4%.
Trajetória ↔ CPC: 497 de 621 cursos (cursos sem Enade no ciclo não têm CPC).

## 3. Fontes e onde colocar cada uma

Fontes declaradas em `config/sources.yml` (não usam a inbox automática, para não depender de nome
de arquivo). Coloque os downloads assim, sem descompactar:

| Pasta | Arquivos | Fonte → tabela | Atenção |
|---|---|---|---|
| `data/landing/inep/censo/` | `microdados_censo_da_educacao_superior_2021..2024.zip` | `censo_cursos` (MT), `censo_ies` | O arquivo de IES muda de nome em 2021; o padrão cobre os dois. Dicionários, PDFs, `md5` e `Thumbs.db` são ignorados |
| `data/landing/inep/trajetoria/` | `indicadores_trajetoria_es_2015_2024.zip` ... `_2020_2024.zip` (6 coortes) | `trajetoria` (MT) | Cabeçalho na linha 9; grão curso × coorte × ano de referência |
| `data/landing/inep/qualidade/` | `CPC_2021`, `cpc_2022`, `CPC_2023`, `IGC_2021`, `igc_2022`, `IGC_2023`, `conceito_enade_licenciaturas.xlsx` | `cpc`, `igc`, `enade_licenciaturas` | Nomes de coluna variam entre anos (2021 tem "Grau acadêmico"); a união é por nome |
| nada a baixar | API do IBGE | `ibge_populacao_idade_mt` | 987 linhas: 141 municípios × idades 18–24 |

Links oficiais:

| Fonte | Download |
|---|---|
| Trajetória, coortes 2015 a 2020 | https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/indicadores_trajetoria_es_2015_2024.zip (troque 2015 por 2016 ... 2020) |
| Censo 2021 a 2024 | https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2024.zip (troque o ano) |
| CPC 2021 / 2022 / 2023 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2021/CPC_2021.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2022/cpc_2022.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2023/CPC_2023.xlsx |
| IGC 2021 / 2022 / 2023 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2021/IGC_2021.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2022/igc_2022.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2023/IGC_2023.xlsx |
| Conceito Enade Licenciaturas 2025 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2025/conceito_enade_licenciaturas.xlsx |
| IBGE SIDRA 9514 | https://sidra.ibge.gov.br/tabela/9514 |

Comandos: `dh.ps1 pipeline` (ingestão + Silver/Gold + testes + exportação).

## 4. Camadas

| Camada | Conteúdo | Quem escreve |
|---|---|---|
| Bronze | Dado fiel ao arquivo, tudo texto, com arquivo de origem e lote | ingestão |
| Silver | Tipado, deduplicado, códigos como texto, nulos tratados | geração automática + dbt |
| Gold | Tabelas para as perguntas P1–P5 e bônus (marts), com contrato | dbt (modelado pela equipe) |
| outputs/ | Extração das marts em CSV e Parquet, com supressão de grupos < 10 | `dh.ps1 export` |

## 5. Idempotência

- Cada arquivo é identificado pelo SHA-256; a carga e o registro no manifesto acontecem na mesma
  transação. Reexecutar não duplica (prova: `rows_loaded = 0` na segunda execução e
  `select * from ops.file_manifest`).
- Silver e Gold são reconstruídas a partir da Bronze; `dbt build` duas vezes dá o mesmo resultado.
- `outputs/` é ordenado e determinístico: mesmo dado, mesmo arquivo (hash no `_manifest.json`).

## 6. Chaves, junções e granularidade

- Códigos (`CO_CURSO`, `CO_IES`, `CO_MUNICIPIO`, `TP_*`) ficam como texto: preserva zeros à esquerda e evita somar código.
- Ligações: Trajetória, Censo cursos e CPC/Enade por código do curso; Censo IES e IGC por `CO_IES`; IBGE por município (7 dígitos).
- Taxa de junção medida e testada:

```sql
{{ dh_join_rate(ref('stg_trajetoria'), 'co_curso', ref('stg_censo_cursos'), 'co_curso') }}
```

```yaml
- name: co_curso
  data_tests:
    - dh_join_coverage:
        arguments: { to: ref('stg_censo_cursos'), field: co_curso, min_ratio: 0.9 }
        config: { severity: warn }
```

- Antes de somar, confirmar o grão de cada tabela (curso × ano não soma com curso × coorte).

## 7. Qualidade

- Testes dbt de não nulo, unicidade e faixa; aviso quando valores não cabem no tipo inferido.
- `gold.dh_catalogo_dados`: tipo, taxa de nulos e cardinalidade de cada coluna (base da exploração).

## 8. Regras do desafio

- Nenhum grupo com menos de 10 alunos em tabela ou gráfico: a exportação remove essas linhas
  (`config/exports.yml`, `min_cell_column`).
- Dados agregados: escrever "está associado a", nunca "causa".
- Dados fora do Git; o README diz de onde baixar.

## 9. Exploração (preencher na Fase 1)

| Fonte | Arquivos | Linhas | Colunas | Nulos relevantes | Chave e grão | Observações |
|---|---|---|---|---|---|---|
| Trajetória | | | | | | |
| Censo cursos | | | | | | |
| Censo IES | | | | | | |
| CPC / Enade | | | | | | |
| IGC | | | | | | |

Consultas úteis: `select source, rows_loaded from ops.ingestion_runs`, `select * from gold.dh_catalogo_dados`.
