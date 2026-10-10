# Consulta à IA: auditoria da Gold, conexão do BI e documentação final

| Campo | Valor |
|---|---|
| Ferramenta | Claude (claude.ai, modo agente com acesso ao repositório, ao terminal e ao GitHub) |
| Quem usou | Fellype Lima da Silva |
| Fase | Fase 3 (Entrega final) |
| Período | 2026-10-10, 14:07 a 16:15 (America/Cuiaba) |
| Objetivo | Auditar os gráficos contra a Gold, corrigir inconsistências, conectar pgAdmin e Superset ao DW, preparar a defesa da arquitetura e atualizar a documentação |

Cada consulta traz o pedido em linguagem técnica, o que a IA respondeu, como a equipe conferiu
e onde a mudança ficou registrada. O texto original de cada pedido está no fim do arquivo.

## 1. Repositório e CI

**C1. Proteger a branch principal (14:24)**
- Pedido: configurar a proteção da `main` sugerida pelo GitHub.
- Resposta: ruleset com bloqueio de exclusão e de force push, sem exigir pull request, para não travar a equipe no dia do evento.
- Validação: ruleset ativo; push normal segue funcionando.

**C2. Diagnosticar o X vermelho do CI (14:28)**
- Pedido: entender a falha marcada no último commit, também exibida no VS Code.
- Resposta: a IA leu os jobs do GitHub Actions. O passo `dbt debug` falhava porque a imagem CLI não tem `git`; trocado por `dbt debug --connection`, que testa só a conexão.
- Validação: o job do laboratório passou no CI seguinte. Commit `cd6a922`.

## 2. Auditoria da Gold e do dashboard

**C3. Conferir cada gráfico contra a Gold e corrigir inconsistências (14:35)**
- Pedido: revisar os 8 blocos do dashboard e corrigir na Gold o que estivesse inconsistente.
- Resposta, erros encontrados e corrigidos:

| Onde | Problema | Correção |
|---|---|---|
| Silver e B2 | `ProUni integral + parcial` resultava vazio quando um dos campos vinha vazio, e o curso saía da soma | Campo vazio conta como zero |
| P1 | Com "Todos" no filtro, o gráfico misturava modalidades e coortes numa linha só | Modalidade e coorte passaram a exigir um valor |
| P5 | "Desistem" aparecia como etapa do funil | Funil: entram → concluem → concluem proficientes; desistentes em nota |
| P4 | "SC" e "Sem CPC" pareciam a mesma categoria | "Sem conceito (SC)" e "Não avaliado" |
| B1 | Só vagas ofertadas, sem medida de alunos | Ingressantes presenciais e ingressantes por 100 jovens |

- Validação: 66 testes Python e 114 nós do dbt passando; outputs regerados no laboratório. Commits `eadc4c8` e `b93d2dc`.

**C4. Confirmar as ressalvas da fonte com consulta direta (14:44 e 14:45)**
- Pedido: rodar o `scripts/diagnostico.sql` e interpretar o resultado.
- Resposta:
  - B2: nenhum curso com FIES ou ProUni vazio; a oscilação anual vem da declaração das IES (ex.: Universidade de Cuiabá com 642, 447, 1.539 e 499 matrículas FIES de 2021 a 2024).
  - P3: o pico de 2023 na rede pública vem de UNEMAT (6.230 desvinculados) e UFMT (4.768), contra cerca de 1.200 nos anos vizinhos.
  - B1: em São José dos Quatro Marcos, uma faculdade declara 937 vagas em Pedagogia com 0 ingressantes.
  - As consultas de P3 e B1 voltaram vazias na primeira vez porque o PowerShell troca a codificação dos acentos; os filtros passaram a usar códigos.
- Validação: rodado de novo no laboratório; ressalvas registradas no README. Commits `a614772` e `69892f6`.

## 3. Conexão ao DW

**C5. Abrir o banco (14:39)**
- Pedido: entender por que o banco não abria em `localhost`.
- Resposta: PostgreSQL não é página web; o acesso é pelo dashboard, pelo pgAdmin ou pelo Superset.

**C6. Conectar pgAdmin e Superset (15:04 a 15:09)**
- Pedido: conectar as ferramentas ao DW.
- Resposta:
  - pgAdmin: host `127.0.0.1`, porta `5433`, banco `datahack`, usuário `dh_bi_reader`, schema `gold`.
  - Superset em Docker: entrar na rede `datahack_warehouse` e usar o host `warehouse`.
  - Erro de senha: comando que copia só a senha do `.env` para a área de transferência, sem exibir o valor.
- Validação: `select count(*) from gold.b1_desertos_municipio` retornou 141.

**C7. Entender um comando de teste de rede (15:14)**
- Pedido: explicar `docker run --rm node:22-alpine npm ping ...`.
- Resposta: testa se um container alcança o registro do npm; não faz parte do projeto.

## 4. Superset e respostas de outra IA

**C8. "Metadados" nos cards do Superset (14:51 e 15:21)**
- Pedido: saber se os indicadores existem ou se há erro de conexão.
- Resposta: "Metadados" é a tradução de "No data". A consulta roda, mas o dataset aponta para outro banco ou schema; não é falha de conexão. Entregues o SQL do dataset B1 e os valores esperados.
- Validação: valores conferidos no pgAdmin (141 municípios, 101 sem oferta, 20,57 vagas por 100 jovens).

**C9. Erro no chat do Superset (15:16)**
- Pedido: entender o erro do botão "Pergunte aos dados".
- Resposta: causas prováveis: container sem internet, falta de chave da API da IA ou dataset errado. O chat ficou fora do escopo da entrega.

**C10. Validar números gerados pelo chat do Superset (15:29)**
- Pedido: comparar com a Gold as respostas que o chat deu ao colega.
- Resposta:

| Indicador | Chat do Superset | Gold publicada |
|---|---|---|
| B1: municípios sem vaga presencial | 76 | 101 |
| B1: vagas por 100 jovens | 12,4 | 20,57 |
| P5: ingressantes em licenciatura | 2.887 | 7.928 |
| P5: proficiência no Enade | "vazia" | 59,3% |

  Conclusão: o Superset lia outra carga. A tabela `controle_atualizacao` ganhou arquivos e linhas disponíveis por fonte, porque "0 linhas na última execução" era lido como fonte vazia.
- Validação: números do chat rejeitados; reimportação pedida ao colega. Commit `25367d1`.

**C11. Publicar para o deploy (15:35 a 15:45)**
- Pedido: mensagem curta para o colega e a sequência para atualizar o deploy.
- Resposta: `git pull`, `dh.ps1 pipeline`, commit e push dos `outputs/`; valores de conferência para o colega.
- Validação: publicada a versão `20261010T194732Z-ed5811`. Commit `598cf69`.

## 5. Defesa e documentação

**C12. Justificar cada ferramenta (15:46)**
- Pedido: o que cada ferramenta faz e por que foi escolhida.
- Resposta: para cada peça, o que faz, por que e a resposta para "por que não X" (ex.: Spark seria custo sem ganho num volume de milhares de linhas).
- Validação: usado no pitch.

**C13. Explicar as três Gold e a `ops` (15:54)**
- Pedido: explicar `gold_candidate`, `gold`, `gold_previous` e `ops`.
- Resposta: candidato testado, versão publicada e versão anterior para rollback; `ops` como trilha de auditoria de execuções, arquivos e publicações.
- Validação: texto incluído no README. Commit `69892f6`.

**C14. Atualizar toda a documentação (15:56)**
- Pedido: deixar todos os README alinhados à versão publicada.
- Resposta: README com resultados e ressalvas da fonte; arquitetura, estratégia e runbook atualizados.
- Validação: revisado pelo autor. Commit `69892f6`.

**C15. Registrar o uso de IA (16:04 e 16:15)**
- Pedido: registrar as consultas em `prompts/` no formato da apresentação, de forma técnica e fácil de ler.
- Resposta: um arquivo por sessão, com pedido técnico, resposta, validação e commit, e o texto original no fim.
- Validação: revisado pelo autor.

## O que foi aproveitado ou corrigido

| Tipo | Item |
|---|---|
| Corrigido na Gold | Perda de cursos na soma de ProUni e financiamento; rótulos de CPC; B1 com ingressantes |
| Corrigido no dashboard | Séries misturadas no P1; etapa errada no funil P5 |
| Corrigido no CI | `dbt debug` sem depender de `git` |
| Rejeitado | Números do chat do Superset, por divergirem da Gold testada |
| Confirmado na fonte | Ressalvas de B1, P3 e B2 com consulta direta na Silver |

## Texto original dos pedidos

<details>
<summary>Prompts como foram digitados</summary>

| Consulta | Texto original |
|---|---|
| C1 | (print do aviso "Your main branch isn't protected") |
| C2 | "outra a b1 e as p não não ta funcionando? conectei via superset não deu .e o meu vs ta com isso?" |
| C3 | "o que é pra fazer e confira esses pontos e corrija na gold se tem algo incossitente. e o que é pra fazer com o docker?" |
| C4 | (log do pipeline e do diagnóstico) / "ele ja pode conectar? no dw ?" |
| C5 | "banco não abriu local host?" |
| C6 | "ajude me conectar" / "?" (erro de senha) |
| C7 | "docker run --rm node:22-alpine npm ping --registry=https://registry.npmjs.org --fetch-timeout=15000 --fetch-retries=0" |
| C8 | "essa tela aparece no super7 confirme se existe eses indicadores ou se esta havendo algum erro de conexão" / "temos que resolver esse problema" / "nao entendi como resolver essa demanda ?" |
| C9 | "o pq ta dando erro no super chat?" |
| C10 | "veja os pontos dos graficos conectados ao supersete o que pode ser e vamos corrigir com coerencia." |
| C11 | "resume o que falar pra ele" / "Ajudeme fazer isto ... O outro PC roda .\scripts\dh.ps1 pipeline com os arquivos do INEP e faz push dos outputs/ na main ..." |
| C12 | "Agora expliqueme o pq de cada ferramenta e framework para que eu possa defendeer a arquitetura e pq  entende?" |
| C13 | "expliqueme esses gold e esse ops?" |
| C14 | "garanta que todos os readme estajem atualizados" |
| C15 | "cade o promts que falei pra voce fazer registrado aqui mais de uma maneira tecnica e sempre como consulta cade coloque como pede a apresentação." / "lapide mais deixe mais tecnico e coerente esses prompt que eu fiz a voce e deixe mais facil da pessoa entender" |

</details>
