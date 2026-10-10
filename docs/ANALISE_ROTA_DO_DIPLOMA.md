# Rota do Diploma.html × Guia do participante → o que mudar para o Superset

Leitura completa de `Rota do Diploma.html` (protótipo) e `artefacts.html` (Guia do participante DataHack UNIVAG 2026), com cada divergência encontrada e o destino dela no Superset.

## 1. O que cada arquivo é

| Arquivo | O que é de fato |
|---|---|
| `Rota do Diploma.html` | Protótipo React empacotado (bundle com React 18, fontes Roboto/Cormorant/Lora e um componente `<x-dc>`). **Todos os números são sintéticos**: saem de `hsh()`/`jit()` (hash do recorte) e de constantes como `BASE_N`, `SD`, `SC`. O rodapé diz "Dados demonstrativos". Nenhum valor dele pode ir para o pitch. |
| `artefacts.html` | O guia do desafio: 5 perguntas obrigatórias (P1–P5), 2 bônus (B1–B2), rubricas, penalidades, dicionários e tokens do **Guia de Estilos UNIVAG v1.1** (azul `#0066CC`, navy `#1A2B5E`, rosa `#E83E8C`…). |

O protótipo é bom como **arquitetura de informação** (navegação por pergunta, filtros por escopo, estados vazio/protegido, método por bloco). Como **cálculo** ele não serve: foi desenhado antes de olhar os dados reais, e em vários pontos pede coisas que as bases do INEP não entregam.

## 2. Divergências, pergunta a pergunta

| # | O protótipo faz | O guia / os dados pedem | Mudança |
|---|---|---|---|
| **P1** | Coorte 2015–2019, KPIs Concluíram/Saíram/Em curso, evolução anual, marca "Maior perda". Taxas com arredondamento por maior resto. | Coorte 2015, presencial, situação em 2024, **em que ano do curso a perda é maior**. | Mantido. No Superset a perda por ano vem de `TADA` ponderada (gráfico "Em que ano do curso a perda é maior?"). Taxa = `Σ(taxa × ingressantes) ÷ Σ ingressantes`, nunca média simples. |
| **P2** | Só **cursos**; coortes 2015–2019; comparação com outras coortes escondida na gaveta "Detalhes". | **Cursos e áreas**, maior **e menor** desistência, coortes 2015–**2020**, comparar **no mesmo ano do curso**. | Adicionados: ranking de áreas, ranking "menor" desistência, matriz rótulo × coorte (heatmap) à vista, coorte 2020. |
| **P3** | Fórmula `(desvinculados + transferidos) ÷ vínculos`. Séries: só Pública/Privada × Presencial/EAD. Sem leitura de ano atípico. | Evasão anual = **desvinculados ÷ (matriculados + desvinculados + transferidos)**. Pede **privada com e sem fins lucrativos** e "há algum ano atípico, e por quê?". | Painel usa a fórmula do guia (e mostra a da Gold ao lado, ver §5) e destaca ano atípico com os gráficos de variação ano a ano. A divisão da privada depende de a Gold trazer a categoria administrativa. |
| **P4** | Só barras por faixa CPC 1–5 + "Sem CPC", janela coorte = CPC − 3. | "Mostre a **relação** e discuta **o que mais pode explicá-la**." | Adicionados: dispersão CPC contínuo × desistência por curso (tamanho = ingressantes), controles por rede e modalidade, **correlação por componente do CPC** (`p4_fatores`, da Gold) e tabela de cobertura. "Sem CPC" ≠ zero. |
| **P5** | Proficiência em **4 níveis** ("Abaixo do básico, Básico, Adequado, Avançado"). | O Enade 2025 Licenciaturas traz **uma** medida: `% de concluintes igual ou acima do Padrão 1`. Os 4 níveis **não existem** na base. | Removidos os 4 níveis. Funil em KPIs (ingressantes → % saiu → participantes → % no padrão) + quadrante curso a curso colorido por área. Aviso fixo: bases e denominadores distintos. |
| **B1** | Filtros globais (rede, área, IES) aplicados às vagas. Lista de municípios curta. | Todos os municípios de MT, zero = sem oferta, EAD por polo. | A Gold já publica o município com zero vagas (`is_deserto`). Painel: KPIs, ranking, faixas de oferta e lista dos maiores desertos por população jovem. Filtros globais não se aplicam a B1. |
| **B2** | "Evasão **com** o programa vs **sem**" (diferença em p.p.). | "Cursos com **mais** financiados evadem menos?" | **Impossível como desenhado**: o Censo por curso não separa desvinculados por financiado. Trocado por comparação **entre cursos**: faixa de % de ingressantes com FIES/ProUni × evasão anual ponderada. |

## 3. Outros desvios do protótipo

- **Filtros e rótulos inventados.** "Instituição A/B/C/D", "Agricultura e veterinária", "Ciências sociais e comunicação" (7 áreas abreviadas). Nos dados reais vêm `NO_IES` e `NO_CINE_AREA_GERAL` (a CINE tem 10 áreas gerais; confirmar na carga). Todos os filtros do Superset leem as colunas reais.
- **Paleta e tipografia.** O protótipo usa azul Tailwind `#2563EB` e laranja `#C46A35` com Roboto. O Guia de Estilos UNIVAG manda `--chart-1…5` (`#0066CC`, `#E83E8C`, `#00AEF0`, `#6F42C1`, `#17A2B8`), cor presa à entidade e mínimo 12 px. O dashboard usa a paleta UNIVAG (`superset_config.py`) e cor fixa para Concluíram/Saíram/Em curso.
- **Células pequenas.** O protótipo suprime `n < 10` ou `desistentes < 10`. Mantido (é conservador e evita a penalidade de −3). No Superset a regra vive no SQL de cada gráfico (`HAVING`), não na tela: nenhum gráfico vaza grupo pequeno.
- **"Associação, não causa".** Está nos textos do protótipo; ficou também nas descrições de cada gráfico (ícone ⓘ) e nos avisos por aba (evita −5).
- **Método por bloco** (definição, população, fórmula, denominador, fonte, limitações). Reaproveitado: vai na descrição de cada gráfico e na aba "Fontes e metodologia".

## 4. O que o Superset não replica (e o substituto)

| No protótipo | No Superset |
|---|---|
| Gaveta "Detalhes" por bloco | Menu ⋮ do gráfico: *Ver como tabela*, *Ver consulta*, *Drill to detail*; cada aba traz a tabela de **bases de cálculo** |
| "Personalizar visão" (arrastar, ocultar, salvar no navegador) | Modo edição do dashboard (só para quem edita). Para a banca: abas fixas por pergunta |
| Filtro principal + "Filtros" recolhível | Filtros nativos na barra lateral, com escopo por aba |
| Exportar PDF (modo impressão) | Menu do dashboard › Baixar (imagem/PDF). **Conferir na sua versão**; o plano B em PDF/vídeo continua obrigatório |
| Estados Carregando/Erro/Sem dados/Protegido | Carregamento e erro nativos; "Sem dados/Protegido" = gráfico vazio + texto de método |
| Destaque de série ao passar na legenda | Legenda clicável do ECharts |

## 5. O dashboard Superset sobre a Gold (o que mudou depois de ler o repositório)

O dashboard lê **direto o schema `gold`** do warehouse, com o papel somente leitura `dh_bi_reader` (ver `superset/README.md`). As armadilhas do guia (códigos como texto, EAD por polo, filtro de graduação, junções com taxa de match, idempotência, células < 10) são responsabilidade do pipeline dbt e já estão lá. O Superset só reagrega, ponderando taxas pelos ingressantes.

Divergências entre a Gold e o guia que **precisam de decisão do time** (o painel mostra a Gold e sinaliza):

| # | Gold | Guia | Impacto |
|---|---|---|---|
| 1 | `p3`: evasão = desvinculados ÷ (matrículas + trancadas + desvinculados + transferidos + falecidos) | desvinculados ÷ (matriculados + desvinculados + transferidos) | Número diferente do gabarito ("Corretude das respostas"). O painel mostra a **fórmula do guia** como principal e a da Gold ("base Gold") na tabela. Decidir qual vale e alinhar o dbt. |
| 2 | `p3`: só Pública/Privada | Privada **com e sem fins lucrativos** | Falta `TP_CATEGORIA_ADMINISTRATIVA` em `p3_rede_modalidade_ano`. Não dá para resolver no Superset. |
| 3 | `p2_desistencia_curso`: só o 4º ano do curso, sem município | comparar no mesmo ano do curso; filtros por município | Cursos só no 4º ano (as áreas aceitam qualquer ano do curso). Filtro de município só existe no B1. |
| 4 | `p4`: coortes 2015–2020 somadas, CPC mais recente do curso | janela do protótipo: CPC do ano Y ↔ coorte Y−3 | Coerente com o dbt; basta descrever assim no pitch. |
| 5 | `b1`: "os 141 municípios de MT" | o protótipo dizia 142 | Conferir contra a tabela 9514 do IBGE antes de afirmar o total. |
| 6 | `outputs/` do repositório é parcial: só a coorte 2020, Censo 2021 e 2023, **B1 vazio**, sem Enade | coortes 2015–2020, Censo 2021–2024 | Faltam cargas (`dh.ps1 import-downloads` + `pipeline`). P5 (proficiência) e B1 ficam vazios até lá. |

## 6. Risco principal: o pitch é em outra sala

O guia exige que o dashboard funcione **sem o banco local da equipe**. O Streamlit lê `outputs/`; o Superset precisa de servidor. Opções, da mais segura para a menos:

1. **Levar o notebook da equipe** (o guia permite) com o `warehouse` e o Superset de pé (`superset/up.ps1`). Testar o HDMI antes.
2. **Publicar na nuvem**: Postgres gratuito (Neon/Supabase; a Gold cabe nos ~0,5 GB) e o container do Superset numa VM, apontando `WAREHOUSE_HOST`/`WAREHOUSE_BI_PASSWORD` para ele. Testar na rede do evento.
3. **Plano B obrigatório (−3 se faltar):** PDF com prints de cada aba ou vídeo de 1–2 min, junto do link do pitch.

## 7. Validar quando os dados completos chegarem

1. **"Desistência" inclui transferência?** O dicionário do INEP não diz. O protótipo assume que sim; confirmar antes de escrever "saíram do curso" no pitch.
2. **Salto de 2023** no Censo: o painel mostra a variação ano a ano (`variacao_evasao_pp`, `variacao_matricula_pct`); investigar a causa antes de explicar.
3. **Cobertura do CPC**: acompanhar quantos cursos caem em "Sem CPC" (aba P4, tabela de cobertura).
4. **Enade 2025**: quando carregar, conferir a ligação por `CO_CURSO` e o tamanho dos grupos (a Gold só publica proficiência com 10+ participantes).
