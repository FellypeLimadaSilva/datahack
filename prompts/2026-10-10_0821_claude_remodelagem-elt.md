# Consulta à IA: remodelagem ELT, validação da Gold e fator social

| Campo | Valor |
|---|---|
| Ferramenta | Claude (claude.ai, modo agente com acesso ao repositório e ao terminal) |
| Quem usou | Fellype Lima da Silva |
| Fase | Fase 1 e Fase 2 (Entregas 1 e 2) |
| Período | 2026-10-10 08:16 a 14:05 (America/Cuiaba) |
| Objetivo | Enxugar a arquitetura para o desafio, adotar ELT com dbt e Airflow, validar os indicadores da Gold contra o INEP e incluir o fator social |
| Registro | Prompts literais do autor (com a grafia original); respostas resumidas em linguagem técnica |

## Consultas

| Nº | Prompt do autor | Objetivo técnico | O que a IA fez | Validação humana e decisão | Evidência |
|---|---|---|---|---|---|
| 1 | "ok como clonar o repositorio to em outro pc" | Reproduzir o ambiente no PC do laboratório | Passo a passo de clone e `dh.ps1 doctor` | Executado no laboratório | — |
| 2 | "precisamos remodelar o que não vamos usar nesta arquitetura configurarr o dbt e ultilizar o elt. mas primeiro deu vamos clonar o repositorio aqui" | Clonar e planejar a remodelagem | Diagnóstico da falha do clone por bundle; troca para clone pelo GitHub | Clone feito pelo GitHub | — |
| 3 | "?" (com erro do `doctor` no PowerShell 5.1) | Corrigir o diagnóstico do ambiente | `doctor` sem abortar quando o Docker Engine está parado | Rodado de novo no laboratório | `6c1838f` |
| 4 | "ta tire o que precisa aqui e vamos ultilizar o ELT e vamos usar dbt e airflow e qual base de dados esta faltando? e garanta e trate desses pontos aqui: ..." (com o parecer técnico de 8 pontos) | Atender o parecer: escopo, grão, portão de qualidade, publicação atômica, afirmações técnicas | Silver e Gold escritas à mão com grão declarado; portão de fontes e de dbt; troca atômica de schema com rollback; corrigidas três afirmações (capacidade medida, TRUNCATE e MVCC, `pg_restore --list` não prova restauração) | Revisado ponto a ponto contra o parecer | `b067fb4`, `f8998e6` |
| 5 | "o que eu preciso fazer da minha parte e o que não recisar do projeto pasta ou arquivos que não vamos ultilizar pode tirar." | Remover o que o desafio não usa | Removidos inbox, modelos automáticos, exemplos de varejo, réplica, alertas, Metabase | Conferido que o CI segue verde | `033e661` |
| 6 | "ok agora explique para mim o pq de elt e não etl e deixe claro nos resdme tambem e me explique cada pasta e arquivo. e a base de dados ta aqui" | Justificar ELT e documentar o repositório | Seção "Por que ELT e não ETL" e mapa de pastas no README; comando `import-downloads` | Lido e aprovado pelo autor | `8d5e35e` |
| 7 | "base de dados aqui e como coloco os colaboradores?" | Carregar coorte 2015 e Enade; dar acesso à equipe | Caminhos de cada arquivo; convite de colaborador no GitHub | Bases copiadas para `data/landing/inep` | — |
| 8 | "?" (lista de colunas do Enade) | Ler o layout real do Enade 2025 | P5 passou a usar o total de concluintes proficientes do arquivo; versão de publicação única por execução | Teste de P5 comparando com o arquivo | `96229ea` |
| 9 | "isso aqui ja ta publicado? quero que me explique de uma forma coerente e resumida o pq de cada tecnologia entende? dbt airflow etc e como esta o DW? preciso ter tudo na ponta da lingua" | Defesa da arquitetura | Justificativa de PostgreSQL, dbt, Airflow, Docker e da publicação atômica | Usado no micro-pitch | — |
| 10 | "Airflow me de mais motivos o pq o airflow é util e o pq de post gre preciso ter falas coerentes na hora dew falar o pq de cada coisa" | Argumentos para a banca | Falas curtas para Airflow (retry, agenda, uma tarefa por fonte) e PostgreSQL | Usado no micro-pitch | — |
| 11 | "Se perguntarem: "Precisava de Airflow para isso?" ... resume pra eu falar mais facil a a parte do airflow" | Resposta curta para a banca | Versão em uma frase | Aceito | — |
| 12 | "nao entendi ele nao vai organiza tarefa se entra aluno novo ou cursos novo?" | Entender a atualização anual | Explicação: novo arquivo do INEP entra na pasta e a DAG reprocessa só a partição nova | Aceito | — |
| 13 | "pra extrair da pra ultilizar as api do ibge etc?" | Confirmar extração por API | Confirmado: IBGE SIDRA 9514 já entra por API com nova tentativa | Aceito | — |
| 14 | "O dbt resume o pq ele é útil?" / "Resume" | Fala curta sobre dbt | Regras em SQL versionado e testado antes de publicar | Aceito | — |
| 15 | "como o fator social pode integrar a pipeline? e os indicadores na camada gold valide se condiz com que pediu na apresentação." | Incluir fator social e validar a Gold contra o enunciado | Fator social a partir das colunas do próprio Censo (escola pública, cotas, apoio social, noturno, FIES/ProUni, PPI); denominador da Trajetória igual ao do INEP (ingressantes menos falecidos); teste que confere TDA, TCA e TAP | Teste passou com diferença máxima de 0,000000005 p.p. | `ee53383` |
| 16 | "mas como entrou como entrou como base de dados se pgou da que a gente extraiu tem que ser veridica senioridade e confiabilidade" | Rastreabilidade do fator social | Linhagem documentada: coluna do Censo, staging, intermediária, Gold | Conferido no `_gold__models.yml` | `59cfc56` |
| 17 | "ta mas essabse mostra tiipo o aluno desisitiu por conta de desistencia por conta do valo queroso saber se esses indicadores na gold faz isso e se faz quero saber ne nossa base faz isso" | Saber se há motivo da desistência | Resposta: o INEP não publica motivo nem dado por aluno; os indicadores mostram associação entre cursos, não causa | Linguagem de associação adotada no pitch | — |
| 18 | "verifique esses pontos." (tabela de bases extras: ProUni, CadÚnico, RAIS/CAGED, Anatel, IPEA) | Avaliar bases adicionais | Avaliação de cada base: grão, chave de junção e risco; recomendação de não incluir no tempo do evento | Decisão do autor: não incluir | — |
| 19 | "entendi e o que tenho que faze rna minha parte para testar a pipiline e entregar para analise para fazer os dashboard." | Roteiro de execução e entrega | Sequência `pipeline`, conferência em `ops`, `outputs/` e push | Executado no laboratório | — |
| 20 | (erros de Git: HEAD.lock e 403 com outro usuário) | Destravar o push | Remoção do lock, troca de credencial do Windows, merge pendente | Push feito | `90c5baa` |
| 21 | "como assim tem stremilit aqui e como vejo?" / "????????" | Abrir o dashboard | `dh.ps1 dashboard`; aviso de esperar a instalação sem Ctrl+C | Dashboard aberto em localhost:8501 | `dfe89d7` |
| 22 | "ok entao esta pronto para analise a gold?" | Liberar a Gold para a análise | Confirmação com ressalvas: vaga ofertada não é aluno (B1), P5 final é estimativa, fator social é associação | Gold liberada para a equipe | `f6e3576` |

## O que foi aproveitado ou corrigido

- Corrigido pela própria validação: o teste contra o INEP mostrou 29 linhas com diferença de até 3,9 p.p.; a causa era o denominador (o INEP desconta falecidos). O cálculo foi ajustado e o teste ficou permanente.
- Corrigido: a parcela de escola pública passou a usar só quem informou a origem escolar.
- Descartado: bases extras sem chave confiável com o curso no tempo do evento.
- Corrigidas três afirmações técnicas do texto anterior, apontadas no parecer.
