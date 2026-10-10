# Como adicionar uma fonte

1. Declare em `config/sources.yml`:

```yaml
  - name: minha_fonte
    kind: file
    description: "O que é e qual o grão: ano x curso."
    required: false
    load_strategy: append
    essential_columns: [nu_ano, co_curso, qt_matricula]
    transforms:
      - { op: filter, column: sg_uf, operator: eq, value: MT }
    file:
      path: inep/minha_fonte
      include: ["arquivo_*.zip"]
      zip_member_pattern: "*.CSV"
      format: csv
      sep: ";"
      encoding: cp1252
```

   - `append` para arquivos (um arquivo por partição: ano, coorte, edição); `full` para APIs.
   - `required: true` só se a publicação não fizer sentido sem ela.
   - Excel do INEP: `skip_rows: auto`, `drop_note_rows: true`, `sheet_name: auto`.
   - Nomes de coluna chegam normalizados: minúsculas, sem acento, `_` no lugar de espaços.

2. Confira sem gravar: `python -m datahack_ingest run minha_fonte --dry-run`.

3. Declare a tabela em `dbt/models/_core__sources.yml` (source `bronze`) e escreva o
   `stg_minha_fonte.sql` com `dh_latest_partition(source('bronze', 'minha_fonte'), 'nu_ano')`,
   tipos explícitos (`dh_to_int`, `dh_to_numeric`, `dh_clean_text`) e códigos como texto.

4. No `_staging__models.yml`, declare o grão com `dh_unique_combination` e `not_null` nas colunas
   essenciais. Testes reprovados bloqueiam a publicação.

5. Se a fonte alimenta um mart, documente em `meta` população, numerador, denominador, período,
   agregação e grão, aplique `dh_mask_count` nas contagens `qt_*` e inclua `dh_no_small_cells`.
   Adicione o mart em `config/exports.yml` e um bloco em `dashboard/layout.json`.

6. `.\scripts\dh.ps1 pipeline`.
