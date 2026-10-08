# ADR 0005 — LGPD: dado fora do Git e PII pseudonimizada na Silver

- **Status:** aceito · **Data:** 2026-10-08

## Decisão
1. Nenhum dado ou segredo versionado (`.gitignore`, hook de pre-commit, gitleaks no CI).
2. PII declarada no catálogo (`pii_columns`) e transformada na Silver com SHA-256 + salt (`DBT_PII_SALT`).
3. O dado original existe apenas na Bronze, inacessível ao BI.
4. Modelos com hash de PII nunca são `view` (definição de view é legível no catálogo do PostgreSQL).

## Consequências
+ Contagem/relacionamento de clientes sem expor CPF.
− Trocar o salt muda todos os hashes (tratar como rotação planejada).
− Pseudonimização não é anonimização: o hash ainda é dado pessoal perante a LGPD; controle de acesso continua necessário.
