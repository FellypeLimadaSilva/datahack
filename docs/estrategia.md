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
| Silver + Gold + 82 testes (dbt) | — | 15 s | |

Por quê: o desafio é sobre MT; o Brasil inteiro (4 anos de Censo + 6 coortes) passaria de 3 GB e
10+ minutos por carga nas máquinas do laboratório, sem uso nas perguntas. Ficam nacionais (pequenos):
Censo IES, CPC e IGC, úteis para comparar MT com o Brasil. Para voltar ao nacional, basta remover
o `filter` da fonte em `config/sources.yml` e recarregar.

Primeiros números (coorte 2020, MT, presencial, até 2024): 621 cursos, 28.985 ingressantes,
21,7% concluíram e 56,5% desistiram. Junção Trajetória ↔ Censo por código do curso: 99,4%.
Trajetória ↔ CPC: 497 de 621 cursos (cursos sem Enade no ciclo não têm CPC).

## 3. Fontes e onde colocar cada uma

Cada fonte é declarada em `config/sources.yml` com o que a publicação exige dela: se é obrigatória
e quais colunas são essenciais. Coloque os downloads assim, sem descompactar:

| Pasta | Arquivos | Fonte → tabela | Obrigatória | Atenção |
|---|---|---|---|---|
| `data/landing/inep/censo/` | `microdados_censo_da_educacao_superior_2021..2024.zip` | `censo_cursos` (MT), `censo_ies` | sim | O arquivo de IES muda de nome em 2021; o padrão cobre os dois. Dicionários e PDFs dentro do zip são ignorados |
| `data/landing/inep/trajetoria/` | `indicadores_trajetoria_es_2015_2024.zip` ... `_2020_2024.zip` | `trajetoria` (MT) | sim | Cabeçalho na linha 9 e notas de rodapé tratados |
| `data/landing/inep/qualidade/` | `CPC_2021`, `cpc_2022`, `CPC_2023` | `cpc` | sim | Nomes de coluna variam entre anos; a união é por nome |
| `data/landing/inep/qualidade/` | `IGC_2021`, `igc_2022`, `IGC_2023` | `igc` | não | |
| `data/landing/inep/qualidade/` | `conceito_enade_licenciaturas.xlsx` | `enade_licenciaturas` | não (P5) | Layout novo em 2025: as colunas são localizadas por nome; se curso ou proficiência não forem reconhecidos, nada é publicado |
| nada a baixar | API do IBGE | `ibge_populacao_idade_mt` | não (B1) | 987 linhas: 141 municípios × idades 18–24 |

Links oficiais:

| Fonte | Download |
|---|---|
| Trajetória, coortes 2015 a 2020 | https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/indicadores_trajetoria_es_2015_2024.zip (troque 2015 por 2016 ... 2020) |
| Censo 2021 a 2024 | https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_2024.zip (troque o ano) |
| CPC 2021 / 2022 / 2023 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2021/CPC_2021.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2022/cpc_2022.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2023/CPC_2023.xlsx |
| IGC 2021 / 2022 / 2023 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2021/IGC_2021.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2022/igc_2022.xlsx · https://download.inep.gov.br/educacao_superior/indicadores/resultados/2023/IGC_2023.xlsx |
| Conceito Enade Licenciaturas 2025 | https://download.inep.gov.br/educacao_superior/indicadores/resultados/2025/conceito_enade_licenciaturas.xlsx |
| IBGE SIDRA 9514 | https://sidra.ibge.gov.br/tabela/9514 |

Comando único: `.\scripts\dh.ps1 pipeline`.

## 4. Camadas

| Camada | Conteúdo | Quem escreve |
|---|---|---|
| Bronze | Dado fiel ao arquivo, tudo texto, com arquivo de origem, lote e horário de carga | ingestão |
| Silver | Modelos `stg_*` escritos à mão: tipos explícitos, grão declarado e testado, versão vigente de cada partição; `int_*` com acumulados e junções | dbt |
| Gold | Um mart por pergunta (P1–P5, B1, B2) com população, numerador, denominador, período e agregação documentados | dbt, em `gold_candidate` até ser publicado |
| outputs/ | CSV e Parquet da Gold publicada, com versão, fontes (sha256) e metadados dos indicadores | `export`, só após publicação |

## 5. Idempotência

- Cada arquivo é identificado pelo SHA-256; a carga e o registro no manifesto acontecem na mesma
  transação. Reexecutar não carrega nada de novo e os outputs saem com o mesmo hash (teste
  `tests/integration/test_rota_diploma.py`).
- Um arquivo por partição: ano no Censo, coorte na Trajetória, edição no CPC/IGC. Se o INEP
  republicar uma partição, o arquivo novo entra na Bronze ao lado do antigo e a Silver usa o mais
  recente daquela partição; as outras partições não mudam. Dois anos coexistem sem sobrescrita.
- Carga `full` (só o IBGE) troca tudo numa transação; se a API devolver zero linhas, a carga falha
  e a versão anterior fica.
- Interrupção no meio: o arquivo em andamento é revertido e não aparece no manifesto; a próxima
  execução o carrega de novo.

## 6. Chaves, junções e granularidade

| Tabela | Grão declarado (teste de unicidade) |
|---|---|
| `stg_trajetoria` | curso × coorte × ano de referência |
| `stg_censo_cursos` | ano × curso × município de oferta |
| `int_censo_curso_ano` | ano × curso (soma dos municípios; teste de soma igual) |
| `stg_cpc` | edição × curso |
| `int_cpc_curso` | curso (uma edição: a mais recente de 2021–2023) |
| `stg_igc` | edição × IES |

- Códigos (`CO_CURSO`, `CO_IES`, `CO_MUNICIPIO`) ficam como texto.
- Junções sempre num grão único do lado direito, para não multiplicar linhas: Trajetória ↔ CPC usa
  `int_cpc_curso`, nunca `stg_cpc`; Censo entra agregado por curso e ano. Testes de contagem igual
  provam que a junção não duplicou.
- Comparação de coortes sempre no mesmo ano do curso (`nu_ano_curso`, padrão 4º ano), porque a
  coorte 2015 tem 10 anos de acompanhamento e a 2020 tem 5.
- Medido nos dados reais: Trajetória ↔ Censo 617 de 621 cursos (99,4%); Trajetória ↔ CPC 497 de 621.

## 7. Qualidade e portão de publicação

1. Fontes: toda fonte obrigatória precisa ter sido carregada com sucesso nesta execução, ter linhas
   e ter as colunas essenciais. Falhou: o dbt nem roda.
2. dbt: `dbt build` no schema `gold_candidate`. Qualquer erro, teste reprovado ou modelo pulado
   bloqueia.
3. Publicação: só então `gold_candidate` vira `gold` numa única transação (troca de nomes de schema);
   a versão anterior fica em `gold_previous` para `rollback`. A decisão, aprovada ou rejeitada, é
   registrada em `ops.publications` com fontes e resultado de cada portão.
4. Exportação: só da versão publicada.

## 8. Regras do desafio

- Nenhuma célula com menos de 10 alunos: a Gold não publica linhas com base abaixo de 10 e deixa
  vazias as contagens `qt_*` entre 1 e 9; um teste dbt reprova a publicação se alguma escapar, e a
  exportação confere de novo. O dashboard só lê `outputs/`, então filtros e tooltips não têm como
  mostrar o que não foi publicado. Taxas são publicadas quando a base tem 10 ou mais.
- Dados agregados: escrever "está associado a", nunca "causa".
- Dados fora do Git; o README diz de onde baixar.

## 9. Exploração (dados reais carregados)

| Fonte | Arquivos | Linhas (MT na Bronze) | Colunas | Nulos e domínio | Grão | Observações |
|---|---|---|---|---|---|---|
| Trajetória | 1 (coorte 2020) | 3.105 | 31 | nenhum nulo nas contagens | curso × coorte × ano | 621 cursos, todos presenciais; faltam as coortes 2015–2019 |
| Censo cursos | 2 (2021, 2023) | 29.300 | 202 | `QT_SIT_TRANSFERIDO` pequeno | ano × curso × município | EAD aparece uma vez por município de polo |
| Censo IES | 2 | 5.154 (Brasil) | 87 | | ano × IES | Brasil inteiro, porque IES de fora ofertam EAD em MT |
| CPC | 3 (2021–2023) | 27.700 (Brasil) | 40 | 1.874 sem CPC contínuo, 1.730 "SC", 144 sem faixa | edição × curso | nenhum curso repetido entre edições |
| IGC | 1 (2023) | 2.101 | 17 | | edição × IES | |

Consultas úteis: `select * from ops.publications order by published_at desc`,
`select source, status, rows_loaded from ops.ingestion_runs order by started_at desc`.
