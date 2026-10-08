# Como contribuir

## Fluxo

1. `git switch -c feat/<escopo>-<descricao>` a partir da `main` atualizada.
2. `pip install -e ".[dev,dbt]" && pre-commit install` (uma vez).
3. Commits em **Conventional Commits**:
   `feat(ingest): suporte a paginação por cursor` · `fix(dbt): corrige LY em ano bissexto` ·
   `docs: runbook de backup` · `chore(ci): cache do pip` · `refactor`, `test`, `perf`.
4. Abra PR com o template preenchido. CI verde + revisão são obrigatórios para merge.
5. Mudança que altera número publicado na Gold exige aceite do negócio registrado no PR.

## Padrões

- **Python:** Ruff (lint + format), tipagem nas funções públicas, sem `print` fora da CLI, logs estruturados.
- **SQL/dbt:** minúsculas, um model por arquivo, CTEs nomeadas, `ref()`/`source()` sempre, testes na chave de todo model.
- **Nomes:** `stg_` (silver), `dim_`, `fact_`, `mart_` (gold); colunas em snake_case pt-BR; booleanos com `is_`.
- **Segurança:** nada de dado, segredo ou print com dado pessoal no repositório.

## Versionamento

SemVer com tags `vMAJOR.MINOR.PATCH` e Releases no GitHub. Mudança de contrato da Gold = MAJOR.
