# Consulta à IA: remodelagem ELT, validação da Gold e fator social

| Campo | Valor |
|---|---|
| Ferramenta | Claude (claude.ai, modo agente com acesso ao repositório e ao terminal) |
| Quem usou | Fellype Lima da Silva |
| Fase | Fases 1 e 2 (Entregas 1 e 2) |
| Período | 2026-10-10, 08:16 a 14:05 (America/Cuiaba) |
| Objetivo | Enxugar a arquitetura para o desafio, adotar ELT com dbt e Airflow, validar os indicadores da Gold contra o INEP e incluir o fator social |

Registro das consultas que resultaram em decisão ou mudança no projeto, com o pedido em linguagem
técnica, a resposta da IA, a validação da equipe e o commit.

## 1. Arquitetura

**C1. Atender o parecer técnico com ELT, dbt e Airflow**
- Pedido: remodelar a plataforma conforme o parecer técnico de 8 pontos, mantendo dbt e Airflow, adotando ELT e levantando as bases ausentes.
- Resposta:
  - Silver e Gold escritas à mão, cada tabela com grão declarado e testado.
  - Portão de qualidade em duas etapas: fontes obrigatórias completas, depois dbt sem erro, falha ou modelo pulado.
  - Publicação atômica por troca de schema (`gold_candidate` → `gold`, anterior em `gold_previous`), com rollback.
  - Três afirmações técnicas corrigidas: capacidade medida em vez de estimada; ressalva de TRUNCATE com MVCC; `pg_restore --list` não prova restauração, então foi criado o teste de restauração em banco vazio.
  - Bases ausentes identificadas: Trajetória 2015–2019 e Enade das licenciaturas.
- Validação: revisado ponto a ponto contra o parecer; teste ponta a ponta cobrindo rejeição e rollback. Commits `b067fb4` e `f8998e6`.

**C2. Reduzir o escopo ao que o desafio usa**
- Pedido: remover componentes que não respondem às perguntas do desafio.
- Resposta: removidos inbox, modelos gerados automaticamente, exemplos de varejo, réplica, alertas e Metabase.
- Validação: CI verde depois da remoção. Commit `033e661`.

**C3. Registrar a decisão ELT × ETL**
- Pedido: documentar por que ELT e descrever a função de cada pasta e arquivo.
- Resposta: comparação ELT × ETL no README (onde fica a regra, custo de mudança, auditoria, idempotência), mapa do repositório e comando `import-downloads` para posicionar as bases do INEP.
- Validação: revisado pelo autor. Commit `8d5e35e`.

**C4. Diagnóstico de ambiente no Windows PowerShell 5.1**
- Pedido: o `doctor` abortava com `NativeCommandError` quando o Docker Engine estava parado.
- Resposta: verificação de comandos nativos isolada numa função que não interrompe o script.
- Validação: rodado no laboratório. Commit `6c1838f`.

## 2. Bases e qualidade dos dados

**C5. Ler o layout real do Enade 2025**
- Pedido: ajustar a leitura às colunas reais do arquivo do Enade das licenciaturas.
- Resposta: P5 passou a usar o total de concluintes proficientes do próprio arquivo; versão de publicação única por execução.
- Validação: teste de P5 compara o resultado com o arquivo. Commit `96229ea`.

**C6. Integrar o fator social e validar a Gold contra o enunciado**
- Pedido: incluir o fator social no pipeline e conferir se os indicadores respondem às perguntas da apresentação.
- Resposta:
  - Fator social a partir de colunas do próprio Censo (escola pública, cotas, apoio social, noturno, FIES/ProUni, pretos/pardos/indígenas), sem base externa.
  - Taxas da Trajetória no mesmo método do INEP (ingressantes menos falecidos no denominador).
  - Teste `dh_matches_inep_rates`, que confere cada linha contra TDA, TCA e TAP do INEP.
- Validação: o teste achou 29 linhas com até 3,9 p.p. de diferença no cálculo anterior; após o ajuste, a diferença máxima caiu para 0,000000005 p.p. Commit `ee53383`.

**C7. Rastreabilidade do fator social**
- Pedido: garantir que o fator social venha só dos dados extraídos e seja auditável.
- Resposta: linhagem documentada (coluna do Censo → staging → intermediária → Gold); parcela de escola pública calculada sobre quem informou a origem escolar.
- Validação: metadados conferidos em `dbt/models/gold/_gold__models.yml`. Commit `59cfc56`.

**C8. Limite analítico: motivo da desistência**
- Pedido: verificar se a base permite atribuir causa à desistência (por exemplo, custo da mensalidade).
- Resposta: o INEP não publica motivo nem dado por aluno; os indicadores medem associação entre características dos cursos e desistência, não causa.
- Validação: linguagem de associação adotada no dashboard e no pitch.

**C9. Avaliação de bases complementares**
- Pedido: avaliar ProUni, CadÚnico, RAIS/CAGED, Anatel e IPEA.
- Resposta: análise de grão, chave de junção com o curso e risco de cada base; recomendação de não incluir no prazo do evento.
- Validação: decisão do autor de não incluir.

**C10. Liberação da Gold para a análise**
- Pedido: confirmar se a Gold estava pronta para os dashboards.
- Resposta: liberada, com ressalvas: vaga ofertada não é aluno (B1); a última etapa do P5 é estimativa; fator social e P4 são associação; colunas `qt_*` mascaradas não devem ser somadas de novo.
- Validação: Gold liberada para a equipe. Commit `f6e3576`.

## O que foi aproveitado ou corrigido

| Tipo | Item |
|---|---|
| Corrigido pela validação | Denominador da Trajetória: o teste contra o INEP achou a divergência e o cálculo foi ajustado |
| Corrigido | Escola pública calculada sobre quem informou a origem escolar |
| Corrigido | Três afirmações técnicas apontadas no parecer |
| Removido | Componentes genéricos que não respondiam ao desafio |
| Descartado | Bases complementares sem chave confiável com o curso no prazo do evento |
