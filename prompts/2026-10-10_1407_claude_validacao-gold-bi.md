# Consulta à IA: auditoria da Gold, conexão do BI e documentação final

| Campo | Valor |
|---|---|
| Ferramenta | Claude (claude.ai, modo agente com acesso ao repositório, ao terminal e ao GitHub) |
| Quem usou | Fellype Lima da Silva |
| Fase | Fase 3 (Entrega final) |
| Período | 2026-10-10 14:07 a 16:04 (America/Cuiaba) |
| Objetivo | Auditar os gráficos contra a Gold, corrigir inconsistências, conectar pgAdmin e Superset ao DW, preparar a defesa da arquitetura e atualizar a documentação |
| Registro | Prompts literais do autor (com a grafia original); respostas resumidas em linguagem técnica |

## Consultas

| Nº | Hora | Prompt do autor | Objetivo técnico | O que a IA fez | Validação humana e decisão | Evidência |
|---|---|---|---|---|---|---|
| 1 | 14:24 | (print: "Your main branch isn't protected") | Proteger a branch principal | Ruleset com Restrict deletions e Block force pushes, sem exigir PR | Ruleset ativo; push normal segue funcionando | GitHub, Rulesets |
| 2 | 14:28 | "outra a b1 e as p não não ta funcionando? conectei via superset não deu .e o meu vs ta com isso?" | Entender o X vermelho do CI e a falha no Superset | Leu os jobs do GitHub Actions: o passo `dbt debug` falhava porque a imagem CLI não tem `git`; trocado por `dbt debug --connection` | Job do laboratório passou no CI | `cd6a922` |
| 3 | 14:35 | "o que é pra fazer e confira esses pontos e corrija na gold se tem algo incossitente. e o que é pra fazer com o docker?" (8 prints do dashboard) | Auditar cada gráfico contra a Gold | Encontrados e corrigidos: soma de ProUni integral + parcial perdia o curso quando um campo vinha vazio; gráfico P1 misturava modalidades e coortes com "Todos"; funil P5 tratava "Desistem" como etapa; "SC" e "Sem CPC" ambíguos; B1 sem medida de alunos | 66 testes e 114 nós do dbt passando; outputs regerados no laboratório | `eadc4c8`, `b93d2dc` |
| 4 | 14:39 | "banco não abriu local host?" | Abrir o banco | Explicado que PostgreSQL não abre no navegador; acesso por dashboard, pgAdmin ou Superset | Aceito | — |
| 5 | 14:44 | (log do pipeline e do `diagnostico.sql`) | Confirmar as ressalvas da fonte | FIES sem campos vazios: oscilação vem da declaração das IES; consulta de P3 e B1 voltou vazia porque o PowerShell troca a codificação dos acentos; filtros trocados por códigos | Rodado de novo no laboratório | `a614772` |
| 6 | 14:45 | "ele ja pode conectar? no dw ?" (resultado do diagnóstico) | Liberar acesso de leitura | Parâmetros de conexão do `dh_bi_reader`; leitura do diagnóstico: pico de 2023 na rede pública vem de UNEMAT (6.230 desvinculados) e UFMT (4.768); em São José dos Quatro Marcos uma faculdade declara 937 vagas de Pedagogia com 0 ingressantes | Ressalvas incluídas no README | `69892f6` |
| 7 | 14:51 | "essa tela aparece no super7 confirme se existe eses indicadores ou se esta havendo algum erro de conexão" | Diagnosticar o Superset | "Metadados" é a tradução de "No data": o dataset volta vazio, não é falha de conexão; SQL do dataset B1 e valores esperados (141 municípios, 101 sem oferta, 20,57 vagas por 100 jovens) | Conferido no pgAdmin | — |
| 8 | 15:04 | "ajude me conectar" | Conectar ao DW | Passo a passo no pgAdmin (host 127.0.0.1, porta 5433, `dh_bi_reader`) e no Superset (rede `datahack_warehouse`) | Conectado; `select count(*) from gold.b1_desertos_municipio` = 141 | — |
| 9 | 15:09 | "?" (password authentication failed) | Corrigir a autenticação | Comando que copia só a senha do `.env` para a área de transferência, sem expor o valor | Conectado | — |
| 10 | 15:14 | "docker run --rm node:22-alpine npm ping ..." | Entender o comando | Teste de saída do Docker para o npm; não faz parte do projeto | Aceito | — |
| 11 | 15:16 | "o pq ta dando erro no super chat?" | Erro do chat do Superset | Causas prováveis: sem internet no container, sem chave da API da IA, dataset errado | Chat fora do escopo da entrega | — |
| 12 | 15:29 | "veja os pontos dos graficos conectados ao supersete o que pode ser e vamos corrigir com coerencia." (respostas do chat do Superset) | Validar números gerados por outra IA | Comparação com a Gold: B1 76 contra 101 desertos, 12,4 contra 20,57 vagas por 100 jovens, P5 2.887 contra 7.928 ingressantes, Enade "vazio" contra 59,3% de proficientes; conclusão: o Superset lia outra carga. `controle_atualizacao` ganhou arquivos e linhas disponíveis, porque "0 linhas na última execução" era lido como fonte vazia | Números do chat rejeitados; reimportação pedida | `25367d1` |
| 13 | 15:35 | "resume o que falar pra ele" | Mensagem para o colega | Texto curto com os valores de conferência | Enviado | — |
| 14 | 15:43 | "Ajudeme fazer isto ... O outro PC roda .\scripts\dh.ps1 pipeline ... faz push dos outputs/ na main ..." | Publicar para o deploy | Sequência pull, pipeline, add, commit, push | Publicada a versão 20261010T194732Z-ed5811 | `598cf69` |
| 15 | 15:46 | "Agora expliqueme o pq de cada ferramenta e framework para que eu possa defendeer a arquitetura e pq entende?" | Defesa da arquitetura | O que faz, por que e a resposta para "por que não X" de cada peça | Usado no pitch | — |
| 16 | 15:54 | "expliqueme esses gold e esse ops?" | Explicar publicação e auditoria | `gold_candidate`, `gold`, `gold_previous` e `ops` | Texto incluído no README | `69892f6` |
| 17 | 15:56 | "garanta que todos os readme estajem atualizados" | Atualizar a documentação | README, arquitetura, estratégia e runbook alinhados à versão publicada | Revisado | `69892f6` |
| 18 | 16:04 | "cade o promts que falei pra voce fazer registrado aqui mais de uma maneira tecnica e sempre como consulta cade coloque como pede a apresentação." | Registrar o uso de IA | Este registro e os das outras sessões, com o índice | Revisado pelo autor | este commit |

## O que foi aproveitado ou corrigido

- Erros encontrados na auditoria e corrigidos na Gold: perda de cursos na soma de ProUni e financiamento; rótulos ambíguos de CPC; B1 sem medida de alunos.
- Erros de visualização corrigidos: séries misturadas no P1 e etapa errada no funil P5.
- Números de outra IA (chat do Superset) rejeitados por divergirem da Gold publicada e testada.
- Ressalvas da fonte confirmadas com consulta direta na Silver (`scripts/diagnostico.sql`), não por suposição.
