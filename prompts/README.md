# Conversas com IA

Toda conversa com IA usada no projeto fica nesta pasta, um arquivo por sessão, exportado em
`.md`, `.txt`, `.pdf` ou `.json` (ou um `.md` com o link de compartilhamento).

Nome do arquivo: `AAAA-MM-DD_HHMM_ferramenta_tema.md` (ex.: `2026-10-10_0930_claude_ingestao-censo.md`).
Atualize este índice a cada entrega de fase, não só no fim.

| Arquivo | Quem usou | Fase | Objetivo | O que foi aproveitado ou corrigido |
|---|---|---|---|---|
| `2026-10-09_2242_claude_plataforma-dados.md` | | Preparação | Montar a plataforma de ingestão e transformação | |
| `2026-10-10_0821_claude_remodelagem-elt.md` | Fellype | Fase 1 | Revisar a arquitetura contra o parecer técnico e o desafio, enxugar o escopo, escrever Silver e Gold explícitas, portão de qualidade e publicação atômica | Removidos inbox, modelos automáticos, exemplos de varejo, réplica e alertas; corrigidas três afirmações técnicas (capacidade, TRUNCATE, pg_restore --list); fixados grãos, edição de CPC e comparação no mesmo ano do curso |
| `2026-10-10_chatbot-deepseek.md` | | Bônus | Chat com IA (DeepSeek) dentro do dashboard Superset, restrito ao escopo do dashboard | Plano com 3 agentes de pesquisa; serviço FastAPI com SQL validado, widget no Superset, bateria de avaliação |
| `2026-10-10_plano-b-planilhas.md` | | Contingência | Fazer o mesmo dashboard funcionar sem banco de dados, só com planilhas de qualquer formato | Carregador de planilhas (csv, xlsx, xls, ods, parquet, json, zip) para SQLite; mesmo dashboard e chat sobre a nova fonte; as 53 consultas conferidas contra o Postgres; teste com 11 tabelas em 9 formatos |
