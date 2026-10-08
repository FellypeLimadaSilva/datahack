## O que muda
<!-- Resumo objetivo. Título do PR em Conventional Commits: feat(ingest): ..., fix(dbt): ... -->

## Por quê
<!-- Problema de negócio/técnico. Link da issue: Closes #123 -->

## Impacto em dados
- [ ] Muda número publicado na Gold? Se sim, **quem do negócio aceitou** e qual a diferença esperada:
- [ ] Altera contrato de coluna (nome/tipo) consumido pelo BI
- [ ] Exige `--full-refresh` de incremental
- [ ] Nova fonte em `config/sources.yml` (dono, estratégia, PII declarados)

## Checklist
- [ ] `pytest` e `dbt build` passando localmente
- [ ] Nenhum dado, `.env`, token ou senha no diff (LGPD)
- [ ] PII nova tratada na Silver (`dh_hash_pii`) e nunca exposta na Gold
- [ ] Documentação atualizada (README / docs / descrição dos models)

## Evidências
<!-- Saída de dbt build, contagens antes/depois, prints. -->
