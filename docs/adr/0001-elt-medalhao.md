# ADR 0001 — ELT em camadas medalhão (Bronze/Silver/Gold)

- **Status:** aceito · **Data:** 2026-10-10

## Contexto
As bases do INEP mudam de layout entre anos (nome do arquivo de IES em 2021, colunas do CPC,
cabeçalho na linha 9), as regras das perguntas (evasão, conclusão, edição de CPC, ano do curso)
vão ser discutidas e ajustadas durante o dia, e a banca avalia idempotência, validação e
reprodutibilidade.

## Decisão
ELT medalhão no PostgreSQL. A ingestão grava o arquivo como veio (Bronze, tudo texto, com arquivo
de origem e lote); a única transformação antes de gravar é o recorte de MT. Tipos, versões por
partição, junções e indicadores ficam no dbt (Silver e Gold), versionados e testados. O BI só lê
a Gold publicada.

## Consequências
+ Mudar uma regra é editar SQL e rodar o dbt em segundos; não é preciso baixar nem recarregar os
  arquivos (o Censo 2024 tem cerca de 450 MB).
+ Todo número publicado tem trilha até o arquivo do INEP (`_dh_source_file`, `ops.file_manifest`).
+ Testes de qualidade rodam onde o dado está e bloqueiam a publicação.
+ Erro de tipo não perde dado na carga: o texto original fica na Bronze e a Silver mede o que não converteu.
− Mais armazenamento (a Bronze guarda tudo); mitigado pelo recorte de MT (37 a 46 vezes menos disco).
