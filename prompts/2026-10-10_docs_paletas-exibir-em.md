# Registro dos prompts desta sessão (dashboard Rota do Diploma)

Data da sessão: 10/10/2026. Projeto: DataHack UNIVAG 2026, dashboard Apache Superset em `superset/`.
Este arquivo lista os pedidos feitos nesta janela de contexto, na ordem em que chegaram, com a interpretação, o que foi feito e o que ficou pendente.

Arquivos mais mexidos: `superset/build_bundle.js` (gera o pacote), `superset/superset_config.py` (paletas), `superset/docker/reimport.py`, `chatbot/app/knowledge.py`.
Para reaplicar no Superset em uso: `node superset/build_bundle.js` e `docker exec rota-superset-superset-1 python /app/reimport.py --force` (no Git Bash, prefixe com `MSYS_NO_PATHCONV=1`).

---

## Prompt 1 · Paleta do B2/P5 em todo o painel + alternar número e porcentagem

**Texto (com duas capturas de tela anexas: gráficos do B2 e funil do P5):**

> siga estes padroes, para mudar as paletas do restante do dashboards, e preciso que tenha opção de mostrfar por numeros e porcentagens, onde o usuario pode escolher qual opção ele quer ver, porem que venha por padrao em %

**Interpretação**
- As capturas mostram o padrão visual desejado: navy, cinza-azulado e azul médio nas séries, vermelho só em quem desiste, valores sobre as barras.
- Aplicar esse padrão ao restante do painel.
- Criar uma escolha entre **porcentagem** e **número**, com **porcentagem como padrão**.

**O que foi feito**
- Paleta: toda métrica avulsa passou a navy (`#1A2B5E`); séries agrupadas usam os tons de navy do esquema `univag`; vermelho ficou só para "Saíram do curso" e "Desistem". A paleta sequencial (`univag_seq`) foi trocada de azul-claro para navy e cinza, e as duas últimas cores da categórica foram trocadas por tons de navy.
- Filtro nativo **Exibir em** (Porcentagem | Número), primeiro da barra, obrigatório, padrão Porcentagem, válido em todas as abas de análise.
  - Cada dataset com taxa virou um dataset virtual com a coluna `exibicao`.
  - Cada métrica escolhe entre a taxa e a contagem conforme o modo.
  - Contagens puras são divididas por `COUNT(DISTINCT exibicao)` para não dobrar quando não há filtro.
- Cartões de KPI do P1 e do P5 viraram cartões de texto (Handlebars) para a unidade e o subtítulo mudarem junto com o modo.
- Eixos receberam "(% ou nº)" e o formato numérico passou a `,.1~f`. Títulos "de cada 100 que entram" viraram "dos que entram".
- Gráfico de distribuição das matrículas (P3) deixou de usar `stack: Expand` e ganhou a métrica "Participação nas matrículas".
- Estimativas em modo Número (conclusão no P2; desistentes e proficientes no P5) = taxa × base, arredondado.
- Ficaram sempre como taxa: bolhas, correlação do P4 e os cartões "vagas por 100 jovens" do B1.
- Plano B (planilhas): `reimport.py` remove o prefixo `gold.` do SQL dos datasets virtuais; as colunas só do dataset virtual ficam fora do contrato das planilhas. Validadas 121 expressões em SQLite 3.40.
- Chatbot: `knowledge.py` esconde a coluna `exibicao` e usa só a fórmula da taxa.
- Correção encontrada no caminho: o filtro Coorte aparecia como 2015 na barra mas só valia depois de clicar em Aplicar; passou a ter o valor padrão 2015 de verdade.

**Verificação:** Superset local, modos Porcentagem e Número em todas as abas; contagens batendo com o banco (16.253 ÷ 41.918 = 38,8%); requisições de dados retornando 200.

---

## Prompt 2 · Visão geral com todas as perguntas

**Texto:**

> na visao geral, os graficos deve responder todas as perguntas, as abas voce pode deixar, porem na visao geral deve deixar todos os graficos das 5 perguntas e das 2 bonus, porem nao se esqueça, PRECISO DE UM DASHBOARD DE VISTA GERAL

**Interpretação**
- Manter as abas.
- A Visão geral precisa ter gráficos que respondam as 5 perguntas (P1 a P5) e as 2 bônus (B1 e B2).
- Continuar sendo um painel de vista geral (uma tela), não uma página longa.
- "Todos os gráficos" foi lido como pelo menos um gráfico por pergunta, já que reunir os mais de 50 gráficos numa tela tiraria a função de vista geral.

**O que foi feito**
- Linha de 6 cartões e 9 gráficos de 4 colunas, em 3 linhas, uma pergunta por gráfico:

  | | | |
  |---|---|---|
  | P1 · A turma chega ao diploma? | P1 · Em que ano do curso se perde mais? | P2 · Quais cursos mais perdem alunos? |
  | P3 · A evasão anual está subindo? | P4 · A qualidade (CPC) retém? | P5 · Funil das licenciaturas |
  | B1 · Onde estão os desertos? | B2 · Peso do FIES e do ProUni | B2 · Cursos mais financiados evadem menos? |

- Títulos com o código da pergunta; eixos sem título para ganhar espaço; ranking do P2 com 6 cursos.
- P3 e B2 passaram a mostrar presencial e EAD juntos; o filtro "Modalidade (trajetória)" deixou de agir sobre eles. Por isso o cartão de evasão anual agora soma todas as modalidades (28,8%, antes 14,9%, que era só presencial).
- Altura dos cartões ajustada para 17 unidades, porque 14 e 15 cortavam o rótulo.

**Verificação:** com tela de 1920×1080 a página não rola e os 9 gráficos carregam.

**Limitações:** em telas menores que 1080 px pode aparecer rolagem; as legendas de P3 e B2 têm setas porque as séries não cabem de uma vez.

---

## Prompt 3 · Fontes visíveis em todos os gráficos e com texto mais legível

**Texto:**

> as fontes devem aparecer tambaem na sidebar de todos os graficos, as fontes a escrita meio apagado

**Interpretação**
- A fonte dos dados aparece na descrição do gráfico (menu ⋮ → "Mostrar descrição"). Interpretei "sidebar" como esse painel de descrição.
- Dois problemas: alguns gráficos não citavam fonte, e o texto estava com pouco contraste.
- Se "sidebar" significava um painel lateral fixo, isso não foi feito.

**O que foi feito**
- Todos os gráficos passaram a ter fonte (antes, 15 não tinham: os de B1, os de controle do P4, as tabelas de bases, entre outros). A fonte vem num parágrafo próprio, `**Fonte:** …`, no fim da descrição.
  - Quando a descrição já citava a fonte, ela foi movida para esse formato.
  - Quando não citava, entrou uma fonte padrão por dataset.
- CSS: a descrição do gráfico ganhou fundo claro, borda navy e texto escuro. Os textos de apoio em cinza das abas e os cabeçalhos da tabela de fontes foram escurecidos.

**Verificação:** descrição aberta no Superset local, com cor `rgb(33, 37, 41)` sobre fundo claro e a linha "Fonte:" em negrito.

**Limitação:** a descrição continua a um clique (menu ⋮); não encontrei como deixá-la aberta por padrão.

**Observação:** este prompt chegou enquanto o Prompt 2 ainda estava em andamento; os dois foram aplicados juntos na mesma regeneração do pacote.

---

## Prompt 4 · Esta documentação

**Texto:**

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**O que foi feito:** este arquivo, `docs/PROMPTS_SESSAO_DASHBOARD.md`.

---

## Pendências e avisos

- **Sem commit.** As mudanças estão no diretório de trabalho (`build_bundle.js`, `superset_config.py`, `reimport.py`, `knowledge.py`, `bundle/rota_do_diploma.zip`, `bundle/contrato_planilhas.json`, `planilhas/CONTRATO.md`). Nada foi publicado.
- **`chatbot/app/settings_store.py` está apagado** no diretório de trabalho (já estava assim no início da sessão), mas o `main.py` ainda o importa. A imagem do chatbot não foi reconstruída por isso. Enquanto não for restaurado e reconstruído, o bot em execução usa o dicionário antigo; se reiniciar sem reconstruir, ele lerá o novo pacote com o código antigo e verá a coluna `exibicao`.
- **Plano B (planilhas):** as consultas foram validadas em SQLite, mas o Plano B não foi subido de ponta a ponta.
- **Ranking em modo Número:** os gráficos de ranking passam a ordenar pelo total de pessoas, não pela taxa.
- **Painel do navegador do Claude:** a página só renderiza quando há um screenshot (aba em segundo plano pausa a renderização); não é lentidão do app.
