# Sessão: onde encaixar um modelo de IA (DeepSeek) no projeto

- **Ferramenta:** Claude Code (Claude Sonnet 5.5)
- **Data:** 2026-10-10
- **Quem usou:** Mauricio Balboa
- **Fase:** 3 (repositório final e uso de IA)
- **Objetivo:** avaliar se e onde a API do DeepSeek poderia entrar no projeto Rota do Diploma
- **Resultado:** análise apenas. Nenhum arquivo do pipeline, do dbt ou do dashboard foi alterado nesta sessão.

## Contexto lido pela IA antes de responder

`docs/arquitetura.md`, `dashboard/app.py`, `outputs/_indicadores.json`, `prompts/README.md`,
`config/sources.yml`, `src/datahack_ingest/sniff.py`, `docs/ADDING_A_SOURCE.md`, `.env.example`,
`dashboard/layout.json` e as regras de IA, rubrica e penalidades em `docs/referencias/artefacts.html`.

---

## Prompt 1

> quero encaixar um modelo de ia neste projeto, pensando em usar a api do deepsekk, veja como se encaixa isto, e onde posso usar

**Resposta resumida da IA**

- Não usar IA dentro do pipeline (ingestão, dbt, Gold). Os números são determinísticos e idempotentes, e o
  [ADR 0001](../docs/adr/0001-elt-medalhao.md) e o princípio "explícito, não automático" defendem isso.
  A rubrica de reprodutibilidade vale 20 pontos.
- Não usar IA para explicar causa. O guia penaliza causalidade com −5 e células menores que 10 com −3.
- Usos propostos, em ordem de valor:
  1. Leitura de cada bloco do dashboard, em 2–3 frases de associação.
  2. Respostas diretas a P1–P5 e B1–B2 com número e fonte, como rascunho do pitch.
  3. Chat "pergunte aos dados", apenas se sobrar tempo (depende de internet e de API ao vivo).
  4. Descrições das colunas em `_gold__models.yml`, só no desenvolvimento.
- Desenho: um script gera os textos **antes**, a partir de `outputs/` (já mascarado), valida os números e os
  termos causais, e grava `outputs/_narrativas.json` no Git. O dashboard só lê o JSON, sem chamar a API,
  porque o pitch é em outra sala. A chave `DEEPSEEK_API_KEY` fica no `.env`.
- Perguntou qual dashboard vai para a banca (Streamlit ou Superset) e quanto tempo restava.

**O que foi aproveitado ou corrigido:** nada implementado. As decisões abertas são o dashboard entregue e o prazo.

---

## Prompt 2

> se usar deep, para rodar em python para puxar os pipelines, nao daria o certo?

**Resposta resumida da IA**

- Tecnicamente funciona: function calling com ferramentas como `run_pipeline()` que chamam
  `python -m datahack_ingest pipeline` ou `dbt build`.
- Não compensa: a execução deixa de ser determinística, os portões já decidem publicar ou rejeitar sem LLM,
  há custo e dependência de rede, e um modelo com permissão no terminal e no banco quebra o menor privilégio
  (quatro roles).
- Onde a ideia serve: operador opcional na demo, por cima do comando oficial; ajuda para escrever código de
  extrator, entradas de `sources.yml` e testes (revisados por humano); explicar o log quando um portão
  rejeita uma carga.
- Recomendação: manter o pipeline sem LLM.

**O que foi aproveitado ou corrigido:** o usuário questionou o ponto de vista da primeira resposta e a IA
detalhou em que condição a ideia funciona. Nada implementado.

---

## Prompt 3

> mas seria uma ferramenta de extração, de forma automatica, teriamos apenas que alimentar a ia, igual uma ML

**Resposta resumida da IA**

- Corrigiu a analogia: o DeepSeek não aprende com os arquivos do projeto como um modelo de ML treinado. Cada
  chamada só lê o que foi enviado e pode responder diferente.
- Riscos específicos dos arquivos do INEP: cabeçalho na linha 9, notas de rodapé, códigos que perdem zero se
  lidos como número, nomes de arquivo que mudam entre anos e grãos diferentes por base. Um LLM decidindo isso
  a cada execução pode somar no grão errado sem erro.
- O que já é automático sem IA: `sniff.py` (encoding e delimitador por regra) e `skip_rows: auto`.
- Proposta: a IA gera um **rascunho** de `sources.yml`, `stg_*.sql` e testes a partir das primeiras linhas e do
  dicionário; `--dry-run` e os testes do dbt validam; um humano revisa e commita; o pipeline fixo roda sempre
  igual. Indicado para fontes opcionais futuras (Enade 2025, IBGE).

**O que foi aproveitado ou corrigido:** o usuário insistiu na extração automática e a IA separou "IA decide a
cada execução" (não recomendado) de "IA propõe, humano valida" (recomendado). Nada implementado.

---

## Prompt 4

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**Resposta:** este arquivo, mais a linha no índice [prompts/README.md](README.md).

---

## Pontos para defender na banca

- O que muda o resultado (grão, tipos, máscara de células pequenas) é decidido por código escrito e testado,
  não por um modelo.
- Se IA for usada no produto, ela fica depois de `outputs/`, com validação de números e de linguagem causal e
  revisão humana, e o dashboard continua funcionando sem chave de API.
- Os prompts de qualquer uso futuro devem entrar nesta pasta e no índice.
