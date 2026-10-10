# Conversas com IA

Toda conversa com IA usada no projeto fica nesta pasta, um arquivo por sessão, exportado em
`.md`, `.txt`, `.pdf` ou `.json` (ou um `.md` com o link de compartilhamento).

Nome do arquivo: `AAAA-MM-DD_HHMM_ferramenta_tema.md` (ex.: `2026-10-10_0930_claude_ingestao-censo.md`).
Atualize este índice a cada entrega de fase, não só no fim.

Cada registro é organizado por tema e, em cada consulta, traz o pedido em linguagem técnica, o que
a IA respondeu, como a equipe conferiu e o commit em que a mudança entrou. O texto original de cada
prompt, como foi digitado, fica no fim de cada arquivo.

| Arquivo | Quem usou | Fase | Objetivo | O que foi aproveitado ou corrigido |
|---|---|---|---|---|
| `2026-10-09_2242_claude_plataforma-dados.md` | Fellype | Preparação | Montar a plataforma de ingestão e transformação | Aproveitados ingestão com SHA-256, roles, Docker, CI e fonte IBGE SIDRA; escopo genérico (inbox, modelos automáticos, SCD2, réplica) removido depois |
| `2026-10-10_0821_claude_remodelagem-elt.md` | Fellype | Fases 1 e 2 | Revisar a arquitetura contra o parecer técnico e o desafio, ELT com dbt e Airflow, validar a Gold e incluir o fator social | Removidos inbox, modelos automáticos, varejo, réplica e alertas; corrigidas três afirmações técnicas; denominador da Trajetória corrigido para o método do INEP após o teste achar 29 linhas divergentes; escola pública sobre quem informou a origem |
| `2026-10-10_1407_claude_validacao-gold-bi.md` | Fellype | Fase 3 | Auditar os gráficos contra a Gold, conectar pgAdmin e Superset, preparar a defesa e atualizar a documentação | Corrigidas perda de cursos na soma de ProUni, séries misturadas no P1, funil P5 e rótulos de CPC; B1 com ingressantes; ressalvas da fonte confirmadas na Silver; números do chat do Superset rejeitados por divergirem da Gold |

## Como a IA foi usada

| Regra | Como aplicamos |
|---|---|
| A IA propõe, a equipe valida | Toda mudança de número passou pelos 87 testes do dbt e pelo teste ponta a ponta antes de publicar |
| Conferir contra a fonte oficial | As taxas da Trajetória são comparadas linha a linha com TDA, TCA e TAP do INEP |
| Desconfiar de número sem rastro | Respostas do chat do Superset foram comparadas com a Gold e descartadas quando divergiram |
| Sem segredo na conversa | Senhas ficam no `.env`, fora do Git e fora dos prompts |
| Registro por sessão | Pedido técnico, resposta, validação e commit, com o prompt original preservado |
