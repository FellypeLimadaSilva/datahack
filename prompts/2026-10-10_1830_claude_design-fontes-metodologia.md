# Ajustes de design no dashboard: aba Fontes e metodologia e gráfico da Visão geral

- **Ferramenta:** Claude Code (Claude Sonnet 5.5)
- **Quem usou:** Mauricio
- **Data:** 2026-10-10
- **Escopo deste registro:** só os prompts desta janela de contexto. Prompts de janelas anteriores (chat DeepSeek, Plano B, filtros) estão nos outros arquivos desta pasta.

## Prompts, na ordem

### 1. Melhorar o design da aba "Fontes e metodologia"

> preciso que tenha uma melhora de desing nesta tela, remova esses scrolls para ler as infos, textos estao juntos, preciso de melhorias de desing

Enviou também uma captura da aba. Nela, os blocos de texto (Concluíram · Saíram do curso, Desistência por curso e área, etc.) tinham barra de rolagem interna e cortavam a última linha; as colunas da tabela de fontes encostavam umas nas outras ("…Superior" colado em "Coortes…").

**O que foi feito** (em `superset/build_bundle.js`, o gerador do painel):
- Causa dos scrolls: cada bloco de texto do Superset tem altura fixa, menor que o conteúdo. As alturas foram aumentadas e medidas no navegador (1280 px de largura): nenhum bloco rola.
- "Fontes de dados" e "Definições" passaram a ocupar a largura toda; as definições ficam em duas colunas.
- Novo título "Como cada indicador é calculado", com os seis blocos de metodologia em dois por linha.
- CSS novo para texto markdown: espaçamento e cabeçalho da tabela, marcadores nas listas, títulos com faixa azul-marinho, nota de cálculo em caixa cinza, `código` em destaque.
- `node build_bundle.js` e `reimport.py --force` rodados; painel conferido em `http://localhost:8090`.

### 2. Tirar os números de dentro das cores do gráfico da Visão geral (enviado no meio do trabalho)

> este aqui é no visao geral, preciso que remova estes numeros dentro das cores dos graficos

Enviou também uma captura do gráfico "Visão geral · A turma chega ao diploma?", com valores sobre cada segmento (Concluíram, Em curso, Saíram do curso) e um número acima de cada barra.

**O que foi feito:**
- `showValue: false` nesse gráfico. Saíram os números dos segmentos e também os do topo das barras, que eram valores de segmento e não totais. Os valores continuam no tooltip.
- Conferido no navegador após o reimport.

### 3. Documentar os prompts

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**O que foi feito:** este arquivo e a linha correspondente no índice `prompts/README.md`.

## Pontos de atenção

- As alturas dos blocos são fixas no Superset. Em telas bem mais estreitas que 1280 px o scroll pode voltar; a janela de 1888 px da captura original tem folga.
- O gráfico da Visão geral perdeu todos os rótulos fixos. Se quiser só o total acima da barra, é outro ajuste.
- Nada foi commitado: as mudanças estão na árvore de trabalho (`superset/build_bundle.js` e `superset/bundle/rota_do_diploma.zip`).
