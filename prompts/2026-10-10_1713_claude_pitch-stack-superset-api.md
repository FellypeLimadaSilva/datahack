# Sessão: micro pitch de 3 minutos, escolha do Superset e API de dados abertos

- **Ferramenta:** Claude Code (Claude Sonnet 5.5)
- **Data:** 2026-10-10
- **Quem usou:** Mauricio Balboa
- **Fase:** 3 (pitch e documentação)
- **Objetivo:** montar o roteiro do pitch de abertura com a stack do projeto, justificar o Superset frente ao BI mais comum do mercado e entender se o Superset serve para publicar uma API de dados abertos
- **Resultado:** só orientação e texto. Nenhum arquivo de código foi alterado. Esta sessão gerou este documento e a linha no índice `prompts/README.md`.

## Contexto lido pela IA antes de responder

`C:\Users\mauricio.balboa\.claude\projects\...\memory\project-datahack-rota-do-diploma.md` (memória do projeto),
títulos de `docs/ANALISE_ROTA_DO_DIPLOMA.md`, listagem da raiz do repositório e `docker-compose.yml`
(busca por serviços de API). Para este documento, também `prompts/README.md` e os arquivos já existentes em `prompts/`
para copiar o formato.

---

## Prompt 1

Texto escrito pelo usuário:

> docker, python, airflow e bdt
> temos a base>pipeline>wharehouse>superset
> ibge e inep
>
> quero saber como usaremos isto para um micro pitch de inicio, de 3 minutos

(O "bdt" foi interpretado como **dbt**. O fluxo foi digitado como um diagrama de texto, com IBGE e INEP abaixo da seta da base.)

**Resposta resumida da IA**

- Eixo da fala: a stack responde à pergunta "como confiar nesse número?". Cadeia única: `INEP + IBGE → Airflow → dbt → warehouse → Superset`. Docker e Python entram em uma frase ("roda em qualquer máquina, reproduzível").
- Roteiro de ≈ 400 palavras em quatro blocos:
  1. 0:00–0:30, problema (evasão no ensino superior de MT; dados dispersos no INEP e no IBGE);
  2. 0:30–1:30, como (uma linha por peça: Airflow orquestra, Python ingere, dbt transforma e testa, warehouse guarda, Docker reproduz);
  3. 1:30–2:30, demo ao vivo no Superset, com 2 ou 3 achados reais e não todas as perguntas;
  4. 2:30–3:00, fechamento ("dado público, pipeline reproduzível, número rastreável, decisão na tela").
- Cuidados: não citar números do protótipo `Rota do Diploma.html` (dados sintéticos); validar a escala de TDA e se "desistência" inclui transferência; manter plano B (vídeo e PDF) porque o pitch é em outra sala às 17:15; no máximo uma frase por ferramenta; dividir a fala entre duas pessoas.
- Ofereceu: transformar em 3 slides (problema, arquitetura, dashboard) e desenhar o diagrama da arquitetura.

---

## Prompt 2

> preciso justificar o motivo do uso do superset, ao inves de um bi que é o mais comum do mercado

(Interpretado como Power BI, com Tableau como segunda referência.)

**Resposta resumida da IA**

- Argumento central: o entregável é um pipeline de dados reproduzível, e o Superset segue a mesma lógica das outras peças (open source, em contêiner, versionado).
- Seis justificativas: (1) coerência com a stack; (2) reprodutibilidade, um comando sobe tudo; (3) dashboard como código, via `build_bundle.js` e zip de importação versionável no Git, ao contrário de um `.pbix` binário; (4) custo zero, relevante para instituição pública; (5) regra de negócio no dbt e não escondida em medidas DAX, com uma única fonte da verdade nos `mart.*`/`gold.*`; (6) conexão direta ao SQL do warehouse, sem gateway.
- Frase de 10 segundos para o pitch: "o dado já nasce versionado e reproduzível: pipeline, regra de negócio e dashboard são código. Qualquer universidade sobe isso sem pagar licença."
- Resposta pronta para a pergunta "mas o Power BI é o mais usado": o Power BI é excelente para o usuário final, mas o entregável é uma solução adotável e auditável; como o Superset consome a camada dbt, migrar para o Power BI depois troca só a última etapa.
- Pontos fracos admitidos: menor polimento visual e curva para o gestor sem perfil técnico, precisa de servidor (risco do pitch em outra sala) e menos integração com o Microsoft 365.
- Ofereceu um slide "Por que Superset".

---

## Prompt 3

> sobre a api do superset, a ideia era produzir uma api para passarmos nossos dados que serao open sources, para qualquer um que quisesse, como o superset auxili isto na api?

**Resposta resumida da IA**

- Verificou o repositório: não há API de dados no projeto. As únicas "APIs" do `docker-compose.yml` são as internas do Airflow (`airflow-apiserver`).
- Correção de premissa: o Superset **não** ajuda a criar essa API. A REST API dele (`/api/v1/...`) administra o próprio Superset (dashboards, charts, datasets, usuários), exige token JWT, devolve o formato dos charts e ficaria acoplada a ele.
- O que o Superset oferece de forma indireta: embed com guest token ou papel Public (mostra o dashboard, não entrega o dado), exportação CSV/Excel de um chart (pontual) e SQL Lab (só para quem tem conta).
- Desenho proposto: Superset e API como dois consumidores paralelos do mesmo warehouse (`marts/gold → Superset` e `marts/gold → API REST`).
- Opções de API: PostgREST (automática sobre o Postgres, a mais rápida), FastAPI (controle, Swagger em `/docs`; o chat do projeto já usa FastAPI) e Hasura (GraphQL e REST, mais pesado). Recomendação para o prazo: FastAPI ou PostgREST como serviço a mais no `docker compose`, lendo só os dados agregados, com usuário somente leitura.
- Frase para o pitch: o Superset é a visão para quem decide; a API é a porta para quem quer construir em cima, e as duas leem a mesma camada tratada.
- Cuidados: se a API não estiver pronta às 17:00, apresentar como "próximo passo" sem afirmar que existe; publicar só agregados (nada de microdados do INEP) por causa da LGPD.
- Ofereceu montar um serviço FastAPI mínimo (2 a 3 endpoints com Swagger) no `docker-compose.yml`, confirmando antes o nome das tabelas. **Não foi pedido nem feito.**

---

## Prompt 4

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**O que foi feito:** este arquivo, no mesmo formato dos demais de `prompts/`, e a linha correspondente no índice `prompts/README.md`. O texto dos prompts está transcrito como foi escrito, sem correção ortográfica.

---

## Pontos de atenção

- O roteiro do pitch ainda não tem números reais: os achados (P1–P5, B1–B2) precisam sair do Gold, não do protótipo sintético.
- A API de dados abertos é uma ideia pendente. Nada foi implementado; se não ficar pronta, tratar como roadmap no pitch.
- Nada foi commitado nesta sessão.
