# Conversas com IA

Toda conversa com IA usada no projeto fica nesta pasta, um arquivo por sessão, exportado em
`.md`, `.txt`, `.pdf` ou `.json` (ou um `.md` com o link de compartilhamento).

Nome do arquivo: `AAAA-MM-DD_HHMM_ferramenta_tema.md` (ex.: `2026-10-10_0930_claude_ingestao-censo.md`).
Atualize este índice a cada entrega de fase, não só no fim.

Cada registro lista as consultas que resultaram em decisão ou mudança no projeto, organizadas por
tema: pedido em linguagem técnica, resposta da IA, validação da equipe e commit.

| Arquivo | Quem usou | Fase | Objetivo | O que foi aproveitado ou corrigido |
|---|---|---|---|---|
| `2026-10-09_2242_claude_plataforma-dados.md` | Fellype | Preparação | Montar a plataforma de ingestão e transformação | Aproveitados ingestão com SHA-256, roles, Docker, CI e fonte IBGE SIDRA; escopo genérico (inbox, modelos automáticos, SCD2, réplica) removido depois |
| `2026-10-10_0821_claude_remodelagem-elt.md` | Fellype | Fases 1 e 2 | Revisar a arquitetura contra o parecer técnico e o desafio, ELT com dbt e Airflow, validar a Gold e incluir o fator social | Removidos inbox, modelos automáticos, varejo, réplica e alertas; corrigidas três afirmações técnicas; denominador da Trajetória corrigido para o método do INEP após o teste achar 29 linhas divergentes; escola pública sobre quem informou a origem |
| `2026-10-10_1407_claude_validacao-gold-bi.md` | Fellype | Fase 3 | Auditar os gráficos contra a Gold, integrar o BI com menor privilégio e atualizar a documentação | Corrigidas perda de cursos na soma de ProUni, séries misturadas no P1, funil P5 e rótulos de CPC; B1 com ingressantes; ressalvas da fonte confirmadas na Silver; números do chat do Superset rejeitados por divergirem da Gold |
| `2026-10-10_chatbot-deepseek.md` | | Bônus | Chat com IA (DeepSeek) dentro do dashboard Superset, restrito ao escopo do dashboard | Plano com 3 agentes de pesquisa; serviço FastAPI com SQL validado, widget no Superset, bateria de avaliação |
| `2026-10-10_plano-b-planilhas.md` | | Contingência | Fazer o mesmo dashboard funcionar sem banco de dados, só com planilhas de qualquer formato | Carregador de planilhas (csv, xlsx, xls, ods, parquet, json, zip) para SQLite; mesmo dashboard e chat sobre a nova fonte; as 53 consultas conferidas contra o Postgres; teste com 11 tabelas em 9 formatos |

## Como a IA foi usada

| Regra | Como aplicamos |
|---|---|
| A IA propõe, a equipe valida | Toda mudança de número passou pelos 87 testes do dbt e pelo teste ponta a ponta antes de publicar |
| Conferir contra a fonte oficial | As taxas da Trajetória são comparadas linha a linha com TDA, TCA e TAP do INEP |
| Desconfiar de número sem rastro | Respostas do chat do Superset foram comparadas com a Gold e descartadas quando divergiram |
| Sem segredo na conversa | Senhas ficam no `.env`, fora do Git e fora dos prompts |
| Registro por sessão | Pedido técnico, resposta, validação e commit de cada decisão |
