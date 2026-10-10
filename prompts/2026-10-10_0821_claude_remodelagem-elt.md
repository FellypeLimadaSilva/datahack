# Consulta à IA: remodelagem ELT, validação da Gold e fator social

| Campo | Valor |
|---|---|
| Ferramenta | Claude (claude.ai, modo agente com acesso ao repositório e ao terminal) |
| Quem usou | Fellype Lima da Silva |
| Fase | Fases 1 e 2 (Entregas 1 e 2) |
| Período | 2026-10-10, 08:16 a 14:05 (America/Cuiaba) |
| Objetivo | Enxugar a arquitetura para o desafio, adotar ELT com dbt e Airflow, validar os indicadores da Gold contra o INEP e incluir o fator social |

Cada consulta traz o pedido em linguagem técnica, o que a IA respondeu, como a equipe conferiu
e onde a mudança ficou registrada. O texto original de cada pedido está no fim do arquivo.

## 1. Ambiente no laboratório

**C1. Reproduzir o ambiente em outra máquina**
- Pedido: clonar o repositório no PC do laboratório e verificar os pré-requisitos.
- Resposta: o clone por bundle falhou por caminho inexistente; a IA trocou para clone pelo GitHub e rodou o diagnóstico `dh.ps1 doctor`.
- Validação: clone concluído no laboratório.

**C2. Corrigir o diagnóstico no Windows PowerShell 5.1**
- Pedido: o `doctor` abortava com `NativeCommandError` quando o Docker Engine estava parado.
- Resposta: verificação de comandos nativos isolada numa função que não interrompe o script.
- Validação: `doctor` rodado de novo no laboratório. Commit `6c1838f`.

## 2. Arquitetura

**C3. Atender o parecer técnico (8 pontos) com ELT, dbt e Airflow**
- Pedido: remodelar a plataforma conforme o parecer, manter dbt e Airflow, adotar ELT e listar as bases que faltavam.
- Resposta:
  - Silver e Gold escritas à mão, cada tabela com grão declarado e testado.
  - Portão de qualidade em duas etapas: fontes obrigatórias completas, depois dbt sem erro.
  - Publicação atômica por troca de schema (`gold_candidate` → `gold`, anterior em `gold_previous`), com rollback.
  - Três afirmações técnicas corrigidas: capacidade passou a ser medida e não estimada; ressalva de TRUNCATE com MVCC; `pg_restore --list` não prova restauração, então foi criado o teste de restauração em banco vazio.
  - Bases que faltavam: Trajetória 2015–2019 e Enade das licenciaturas.
- Validação: revisado ponto a ponto contra o parecer; teste ponta a ponta cobrindo rejeição e rollback. Commits `b067fb4` e `f8998e6`.

**C4. Remover o que o desafio não usa**
- Pedido: tirar pastas e arquivos sem uso no desafio.
- Resposta: removidos inbox, modelos gerados automaticamente, exemplos de varejo, réplica, alertas e Metabase.
- Validação: CI verde depois da remoção. Commit `033e661`.

**C5. Justificar ELT e documentar o repositório**
- Pedido: explicar por que ELT e não ETL, registrar isso no README e descrever cada pasta e arquivo.
- Resposta: comparação ELT × ETL no README, mapa de pastas e o comando `import-downloads` para copiar as bases do INEP.
- Validação: lido e aprovado pelo autor. Commit `8d5e35e`.

## 3. Bases e qualidade dos dados

**C6. Carregar a coorte 2015 e o Enade; dar acesso à equipe**
- Pedido: onde colocar os novos arquivos e como adicionar colaboradores no GitHub.
- Resposta: caminho de cada arquivo em `data/landing/inep` e passo a passo do convite de colaborador.
- Validação: bases carregadas; ingestão com status `success` em `ops.ingestion_runs`.

**C7. Ler o layout real do Enade 2025**
- Pedido: ajustar a leitura às colunas reais do arquivo do Enade.
- Resposta: P5 passou a usar o total de concluintes proficientes do próprio arquivo; versão de publicação única por execução, com sufixo aleatório.
- Validação: teste de P5 compara o resultado com o arquivo. Commit `96229ea`.

**C8. Integrar o fator social e validar a Gold contra o enunciado**
- Pedido: incluir o fator social no pipeline e conferir se os indicadores respondem às perguntas da apresentação.
- Resposta:
  - Fator social a partir de colunas do próprio Censo (escola pública, cotas, apoio social, noturno, FIES/ProUni, pretos/pardos/indígenas), sem base externa.
  - Taxas da Trajetória no mesmo método do INEP (ingressantes menos falecidos no denominador).
  - Teste `dh_matches_inep_rates`, que confere cada linha contra TDA, TCA e TAP do INEP.
- Validação: o teste achou 29 linhas com até 3,9 p.p. de diferença no cálculo anterior; depois do ajuste, a diferença máxima caiu para 0,000000005 p.p. Commit `ee53383`.

**C9. Garantir a rastreabilidade do fator social**
- Pedido: mostrar que o fator social vem dos dados extraídos e é confiável.
- Resposta: linhagem documentada (coluna do Censo → staging → intermediária → Gold); parcela de escola pública calculada só sobre quem informou a origem escolar.
- Validação: metadados conferidos em `dbt/models/gold/_gold__models.yml`. Commit `59cfc56`.

**C10. Saber se os dados mostram o motivo da desistência**
- Pedido: verificar se a base indica, por exemplo, desistência por causa do valor da mensalidade.
- Resposta: o INEP não publica motivo nem dado por aluno; os indicadores mostram associação entre características dos cursos e desistência, não causa.
- Validação: linguagem de associação adotada no pitch e no dashboard.

**C11. Avaliar bases extras (ProUni, CadÚnico, RAIS/CAGED, Anatel, IPEA)**
- Pedido: verificar se essas bases deveriam entrar.
- Resposta: avaliação de grão, chave de junção com o curso e risco de cada uma; recomendação de não incluir no tempo do evento.
- Validação: decisão do autor de não incluir.

## 4. Defesa da arquitetura

**C12. Justificar cada tecnologia para a banca**
- Pedido: falas curtas e coerentes sobre PostgreSQL, dbt, Airflow, Docker e o estado do DW, incluindo a resposta para "precisava de Airflow?".
- Resposta:
  - Airflow: novas tentativas, agenda e uma tarefa por fonte; a atualização anual do INEP roda sem intervenção.
  - dbt: regras em SQL versionado e testado antes de publicar.
  - PostgreSQL: padrão de mercado, gratuito, do tamanho do volume, com papéis de acesso por camada.
  - API do IBGE: já integrada (SIDRA 9514), com nova tentativa em caso de erro.
- Validação: usado no micro-pitch.

## 5. Execução e entrega

**C13. Roteiro para testar o pipeline e entregar para a análise**
- Pedido: o que rodar para testar e liberar os dados para os dashboards.
- Resposta: sequência `pipeline`, conferência em `ops`, exportação para `outputs/` e push.
- Validação: executado no laboratório.

**C14. Destravar o push**
- Pedido: resolver `HEAD.lock` e erro 403 com credencial de outro usuário.
- Resposta: remoção do lock, troca da credencial salva no Windows e conclusão do merge pendente.
- Validação: push concluído. Commit `90c5baa`.

**C15. Abrir o dashboard**
- Pedido: entender e abrir o Streamlit.
- Resposta: `dh.ps1 dashboard`, com aviso de esperar a instalação sem interromper com Ctrl+C.
- Validação: dashboard aberto em localhost:8501. Commit `dfe89d7`.

**C16. Liberar a Gold para a análise**
- Pedido: confirmar se a Gold está pronta.
- Resposta: liberada, com ressalvas: vaga ofertada não é aluno (B1); a última etapa do P5 é estimativa; fator social e P4 mostram associação; não somar de novo as colunas `qt_*` mascaradas.
- Validação: Gold liberada para a equipe. Commit `f6e3576`.

## O que foi aproveitado ou corrigido

| Tipo | Item |
|---|---|
| Corrigido pela validação | Denominador da Trajetória: o teste contra o INEP achou a divergência e o cálculo foi ajustado |
| Corrigido | Escola pública calculada sobre quem informou a origem escolar |
| Corrigido | Três afirmações técnicas apontadas no parecer |
| Removido | Componentes genéricos que não respondiam ao desafio |
| Descartado | Bases extras sem chave confiável com o curso no tempo do evento |

## Texto original dos pedidos

<details>
<summary>Prompts como foram digitados</summary>

| Consulta | Texto original |
|---|---|
| C1 | "ok como clonar o repositorio to em outro pc" / "precisamos remodelar o que não vamos usar nesta arquitetura configurarr o dbt e ultilizar o elt. mas primeiro deu vamos clonar o repositorio aqui" |
| C2 | "?" (com o erro do `doctor`) |
| C3 | "ta tire o que precisa aqui e vamos ultilizar o ELT e vamos usar dbt e airflow e qual base de dados esta faltando? e garanta e trate desses pontos aqui: ..." |
| C4 | "o que eu preciso fazer da minha parte e o que não recisar do projeto pasta ou arquivos que não vamos ultilizar pode tirar." |
| C5 | "ok agora explique para mim o pq de elt e não etl e deixe claro nos resdme tambem e me explique cada pasta e arquivo. e a base de dados ta aqui" |
| C6 | "base de dados aqui e como coloco os colaboradores?" |
| C7 | "?" (com a lista de colunas do Enade) |
| C8 | "como o fator social pode integrar a pipeline? e os indicadores na camada gold valide se condiz com que pediu na apresentação." |
| C9 | "mas como entrou como entrou como base de dados se pgou da que a gente extraiu tem que ser veridica senioridade e confiabilidade" |
| C10 | "ta mas essabse mostra tiipo o aluno desisitiu por conta de desistencia por conta do valo queroso saber se esses indicadores na gold faz isso e se faz quero saber ne nossa base faz isso" / "entendi e esses indicadores mostra isso?" |
| C11 | "verifique esses pontos." / "nao entendi resume" |
| C12 | "isso aqui ja ta publicado? quero que me explique de uma forma coerente e resumida o pq de cada tecnologia entende? dbt airflow etc e como esta o DW? preciso ter tudo na ponta da lingua" / "Airflow me de mais motivos o pq o airflow é util e o pq de post gre preciso ter falas coerentes na hora dew falar o pq de cada coisa" / "Se perguntarem: "Precisava de Airflow para isso?" ... resume pra eu falar mais facil a a parte do airflow" / "nao entendi ele nao vai organiza tarefa se entra aluno novo ou cursos novo?" / "quero falar o airflow vai servi pra isso e tal tal entende?" / "pra extrair da pra ultilizar as api do ibge etc?" / "O dbt resume o pq ele é útil?" / "Resume" |
| C13 | "entendi e o que tenho que faze rna minha parte para testar a pipiline e entregar para analise para fazer os dashboard." |
| C14 | (saídas de erro do Git: `HEAD.lock` e 403) |
| C15 | "como assim tem stremilit aqui e como vejo?" / "????????" / "streamilit deu certo. ..." |
| C16 | "ok entao esta pronto para analise a gold?" |

</details>
