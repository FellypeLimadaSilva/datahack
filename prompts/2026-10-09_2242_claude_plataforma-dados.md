# Consulta à IA: montagem da plataforma de dados

| Campo | Valor |
|---|---|
| Ferramenta | Claude (claude.ai, modo agente com acesso ao repositório) |
| Quem usou | Fellype Lima da Silva |
| Fase | Preparação (antes do evento) |
| Período | 2026-10-08 15:59 a 2026-10-10 00:11 (America/Cuiaba) |
| Objetivo | Montar a plataforma de ingestão e transformação que seria usada no desafio |
| Registro | Reconstruído a partir do histórico de commits do repositório; a conversa original fica na exportação do claude.ai da conta do autor |

## Consultas

| Nº | Quando | Pedido (resumo técnico) | O que a IA entregou | Validação humana e decisão | Evidência |
|---|---|---|---|---|---|
| 1 | 10-08 15:59 | Plataforma ELT medalhão em PostgreSQL com dbt e Airflow, em Docker, com papéis de banco por camada | Estrutura inicial: ingestão Python, Bronze/Silver/Gold, roles, Airflow, CI | Aceito como base | `9dbaff6` |
| 2 | 10-08 16:55 | Cobrir cenários gerais de dados (exclusões, histórico, alta disponibilidade) | ETL na ingestão, SCD2, novos formatos, alertas, réplica | Aceito na época; removido depois por não servir ao desafio (ver sessão de remodelagem) | `d6c318c` |
| 3 | 10-09 17:20 | Ingestão sem configuração para qualquer arquivo | Inbox e Silver/Gold geradas automaticamente | Removido depois: modelos automáticos não têm grão declarado nem testes de negócio | `78bbb2b` |
| 4 | 10-09 23:05 | Adaptar ao desafio Rota do Diploma: fontes do INEP, outputs e roteiro de laboratório | Catálogo das fontes INEP, export para `outputs/`, `docs/LAB_SETUP.md` | Aceito | `e62c2ec` |
| 5 | 10-09 23:18 | Links oficiais de cada base | Links do INEP e do IBGE na documentação | Conferidos manualmente nos portais | `95bba44` |
| 6 | 10-09 23:40 | Fonte para o bônus B1 (população jovem por município) | API IBGE SIDRA tabela 9514, 18 a 24 anos, municípios de MT | Aceito; conferido contra a tabela no SIDRA | `be67bc0` |
| 7 | 10-10 00:09 | Validar o catálogo com os arquivos reais baixados | Ajuste de padrões de arquivo, abas e cabeçalhos | Aceito após rodar a ingestão nos arquivos reais | `7872e27` |
| 8 | 10-10 00:11 | Erro: cabeçalho das planilhas do INEP lido na linha errada | Correção do detector de cabeçalho (linha anterior ao bloco de dados) | Aceito; coberto por teste unitário | `3de6944` |

## O que foi aproveitado ou corrigido

- Aproveitado: ingestão com manifesto SHA-256, papéis de banco, Docker, CI e a fonte IBGE SIDRA.
- Corrigido depois, na remodelagem: escopo genérico demais para o desafio (inbox, modelos automáticos, SCD2, réplica, alertas).
