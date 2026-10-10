# Estratégia de ingestão e transformação (Fase 1)

Pergunta central: de cada 100 que entram numa graduação em Mato Grosso, quantos chegam ao diploma,
e em quais cursos a rota se perde?

## 1. Stack e justificativa

| Escolha | Por quê | Alternativa considerada |
|---|---|---|
| PostgreSQL 16 (Docker) | Aguenta o Censo 2024 (~450 MB de CSV, 2–3x em disco) com folga; cast seguro (`pg_input_is_valid`) que não derruba a carga; transação por arquivo garante idempotência; roles separam ingestão, transformação e leitura | DuckDB: mais simples e rápido para análise local, mas sem controle de acesso por camada e sem concorrência de escrita |
| Python (`datahack-ingest`) | Ingestão por código, lendo xlsx/CSV/zip em streaming, com manifesto de arquivos | pandas solto em notebook: não é idempotente nem auditável |
| dbt | Transformações versionadas, testes de qualidade como gate, documentação gerada | SQL solto: sem testes nem linhagem |
| Dashboard lendo `outputs/` | Abre no pitch sem acesso ao banco (Caminho 1) | Conectar direto no banco: falha fora do laboratório |

## 2. Fontes e onde colocar cada uma

### Links oficiais (confira com `fontes_dados.html` do evento)

| Fonte | Download |
|---|---|
| Trajetória (2020–2024) | https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/indicadores_trajetoria_es_2020_2024.zip |
| Trajetória (página) | https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais/indicadores-de-trajetoria-da-educacao-superior |
| Censo 2021 | https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2021.zip |
| Censo 2022 | https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2022.zip |
| Censo 2023 | https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2023.zip |
| Censo 2024 | https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2024.zip |
| CPC 2021 / 2022 / 2023 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2021/CPC_2021.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2022/cpc_2022.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2023/CPC_2023.xlsx |
| IGC 2021 / 2022 / 2023 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2021/IGC_2021.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2022/igc_2022.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2023/IGC_2023.xlsx |
| IDD 2021 / 2022 / 2023 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2021/IDD_2021.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2022/idd_2022.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2023/IDD_2023.xlsx |
| Conceito Enade Licenciaturas 2025 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2025/conceito_enade_licenciaturas.xlsx |
| IBGE SIDRA 9514 | https://sidra.ibge.gov.br/tabela/9514 (consulta) · https://servicodados.ibge.gov.br/api/docs/agregados?versao=3 (API) |

Organize em `data/landing/inbox/` (fora do Git):

| Fonte | Formato | Onde colocar | O que a plataforma faz | Atenção |
|---|---|---|---|---|
| Indicadores de Trajetória (coortes 2015–2020) | `.xlsx`, cabeçalho na linha 9 | `inbox/trajetoria/` (todos os arquivos) | Uma tabela; cabeçalho e notas de rodapé detectados | Granularidade: curso × coorte × ano de referência |
| Censo da Educação Superior 2021–2024 | zip com CSV `;` latin-1 | `.zip` soltos na raiz de `inbox/` | Separa cursos e IES em tabelas próprias, junta os 4 anos, ignora dicionário e leia-me | Curso × ano; 2024 é o maior arquivo |
| CPC 2021–2023 e Enade 2025 | `.xlsx` soltos | `inbox/cpc/`, `inbox/enade/` | Uma tabela por pasta | Nomes de coluna podem mudar entre anos: confira a união |
| IGC 2021–2023 | `.xlsx` | `inbox/igc/` | Uma tabela | Granularidade: instituição |
| IBGE SIDRA (tabela 9514) | JSON da API | fonte `kind: api` em `config/sources.yml` | Ingestão com retry e paginação | Opcional (bônus B1) |

Recorte de Mato Grosso já na ingestão (ETL), para economizar disco e tempo: `inbox/_sources.yml`

```yaml
microdados_cadastro_cursos:
  transforms:
    - { op: filter, column: sg_uf, operator: eq, value: MT }
```

Confirme o nome da coluna no dicionário antes. Decisão a registrar: cursos EAD de instituições de
fora com polo em MT podem ficar de fora desse filtro.

Comandos: `dh.ps1 discover` (mostra o que cada arquivo vai virar), `dh.ps1 pipeline`.

## 3. Camadas

| Camada | Conteúdo | Quem escreve |
|---|---|---|
| Bronze | Dado fiel ao arquivo, tudo texto, com arquivo de origem e lote | ingestão |
| Silver | Tipado, deduplicado, códigos como texto, nulos tratados | geração automática + dbt |
| Gold | Tabelas para as perguntas P1–P5 e bônus (marts), com contrato | dbt (modelado pela equipe) |
| outputs/ | Extração das marts em CSV e Parquet, com supressão de grupos < 10 | `dh.ps1 export` |

## 4. Idempotência

- Cada arquivo é identificado pelo SHA-256; a carga e o registro no manifesto acontecem na mesma
  transação. Reexecutar não duplica (prova: `rows_loaded = 0` na segunda execução e
  `select * from ops.file_manifest`).
- Silver e Gold são reconstruídas a partir da Bronze; `dbt build` duas vezes dá o mesmo resultado.
- `outputs/` é ordenado e determinístico: mesmo dado, mesmo arquivo (hash no `_manifest.json`).

## 5. Chaves, junções e granularidade

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

## 6. Qualidade

- Testes dbt de não nulo, unicidade e faixa; aviso quando valores não cabem no tipo inferido.
- `gold.dh_catalogo_dados`: tipo, taxa de nulos e cardinalidade de cada coluna (base da exploração).

## 7. Regras do desafio

- Nenhum grupo com menos de 10 alunos em tabela ou gráfico: a exportação remove essas linhas
  (`config/exports.yml`, `min_cell_column`).
- Dados agregados: escrever "está associado a", nunca "causa".
- Dados fora do Git; o README diz de onde baixar.

## 8. Exploração (preencher na Fase 1)

| Fonte | Arquivos | Linhas | Colunas | Nulos relevantes | Chave e grão | Observações |
|---|---|---|---|---|---|---|
| Trajetória | | | | | | |
| Censo cursos | | | | | | |
| Censo IES | | | | | | |
| CPC / Enade | | | | | | |
| IGC | | | | | | |

Consultas úteis: `select source, rows_loaded from ops.ingestion_runs`, `select * from gold.dh_catalogo_dados`.
