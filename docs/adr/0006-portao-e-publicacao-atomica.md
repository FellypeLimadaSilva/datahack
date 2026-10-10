# ADR 0006 — Portão de qualidade e publicação atômica da Gold

**Status:** aceito (2026-10-10)

**Contexto.** Com o dbt escrevendo direto na Gold, basta uma fonte ter sucesso para o build rodar,
e os testes de dados só acontecem depois que o modelo foi materializado. O BI podia ver resultado
calculado com base incompleta, de versões diferentes, ou reprovado nos testes.

**Decisão.** O dbt constrói a Gold em `gold_candidate`. A publicação exige: (1) toda fonte
obrigatória carregada com sucesso nesta execução, com linhas e colunas essenciais; (2) `dbt build`
sem erro, falha ou modelo pulado. Aprovada, uma transação renomeia `gold` para `gold_previous` e
`gold_candidate` para `gold` e refaz as permissões do BI. Toda decisão vai para `ops.publications`.
A exportação para `outputs/` só lê a versão publicada.

**Consequências.** Falha preserva a última versão válida no banco e em `outputs/`; `rollback` troca
de volta. Consultas em andamento terminam na versão antiga. O `dh_transformer` precisa de `CREATE`
no banco para renomear schemas. Os modelos da Gold são tabelas, para não depender de views da
Silver que o dbt recria.
