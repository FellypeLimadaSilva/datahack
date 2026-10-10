# Sessão: chat com IA (DeepSeek) dentro do dashboard

- **Ferramenta:** Claude Code (app desktop), modelo Sonnet 5.5
- **Quem usou:** Mauricio Balboa
- **Data:** 2026-10-10
- **Objetivo da sessão:** colocar um chatbot com IA dentro do dashboard Superset da Rota do Diploma, que responde só sobre o dashboard, com a chave da DeepSeek configurada pelo navegador.
- **Resultado final:** um único endereço (`http://localhost:8088`) com o dashboard e o chat; configuração da chave em *Settings → Manage → Configurações do chat (IA)*; respostas estruturadas com fonte pública (INEP, IBGE); geração de imagens (mapa mental, barras, linhas, pizza).

> Segredos (senha do admin, chave da DeepSeek, tokens) **não** estão neste arquivo, de propósito.

## Resumo dos prompts

| # | Prompt (resumo) | O que mudou no projeto |
|---|---|---|
| 1 | O Superset tem chatbot com IA ou preciso de uma API? | Pesquisa: o Superset 4.1.2 não tem chat nativo; o caminho é um serviço próprio chamando uma API de LLM |
| 2 | Preparar o ambiente para a API do DeepSeek, explicar como "treinar" e usar agentes | 3 agentes de pesquisa, plano aprovado e serviço `chatbot/` (FastAPI) criado |
| 3 | "O banco está funcional no repositório, use já para o teste" | Gold real do warehouse carregada com os CSVs de `outputs/` |
| 4 | Aba de configurações com chave de API, farol e status do banco | Aba Configurações no chat, farol cinza/verde/vermelho/laranja e painel de status |
| 5 | Onde você subiu o local? | Explicação das portas e containers |
| 6 | Por que 4 links? Quero um sistema integrado | `gateway/` (nginx) e `dh.ps1 app`: endereço único `:8088` |
| 7 | Onde está a configuração? Não está em Settings | Entrada no menu *Settings → Manage* do Superset e página `/assistente/configuracoes` |
| 8 | Nada em `.env`; tudo no front ligado ao back | Fim do token de admin e das variáveis `DEEPSEEK_*`; acesso pela sessão de admin do Superset |
| 9 | Qual o login do admin? | Resposta com usuário e onde fica a senha |
| 10 | Erro 422 no chat | Corrigido o limite de tamanho do histórico |
| 11 | A IA deve responder tudo, até para leigo | Porteiro de escopo permissivo e instruções para perguntas soltas |
| 12 | Resposta mal estruturada; mostrar fonte (INEP, IBGE), não tabelas | Formato fixo com emojis, tabelas renderizadas, fontes públicas |
| 13 | Gerar imagens (mapa mental) sobre o dashboard | Ferramenta `criar_imagem` e desenho em SVG com download PNG |
| 14 | Documentar todos os prompts desta janela | Este arquivo |

---

## Prompts, na íntegra

### 1. A pergunta inicial

> quero colocar um chatbot com ia integrada para responder usuarios com duvidas ou ate mesmo formas mais rapidas de achar, o superset faz esta integração? ou eu teria que puxar uma api para isto?

- **Intenção:** saber se dá para ter um assistente de IA dentro do Superset sem montar tudo do zero.
- **O que foi feito:** pesquisa na documentação oficial e leitura do `superset_config.py`. A conclusão foi que o Superset não traz chat embutido (só o servidor MCP para assistentes externos), então é preciso um serviço próprio que chame uma API de LLM.
- **Aproveitado:** a decisão de arquitetura (serviço separado + botão dentro do dashboard).

### 2. Preparar o ambiente, "treinar" o modelo e usar agentes

> prepara o ambiente para ser alimentado pela api do deepseek, e me passa como treinar este modelo do deepseek para responder perguntas somente do dashboard que ele vai interagir, por enquanto use agentes para isto, dispare agentes sobre como podemos implementar uma ia dentro do nosso dash para isto, e me retorne perguntas se surgir

- **Intenção:** planejar com agentes antes de construir, entender o "treinamento" e receber perguntas em caso de dúvida.
- **O que foi feito:** 3 agentes de pesquisa em paralelo (mapa do repositório e da camada gold; formas de embutir o chat no Superset; API da DeepSeek e restrição de escopo). A DeepSeek não tem fine-tuning na API oficial e ele não imporia escopo; o "treino" é prompt de sistema, dicionário de dados, SQL validado, porteiro de escopo e bateria de avaliação.
- **Perguntas respondidas por você no plano:**
  - Consulta: **SQL gerado e validado** (em vez de consultas fixas).
  - Interface: **botão flutuante no Superset**.
  - Runtime: **container Python/FastAPI**.
  - Privacidade: **aceitar sem aviso extra** (a DeepSeek processa na China; fica só a proteção da chave).
- **Resultado:** serviço `chatbot/` com validador de SQL (`sqlglot`), dicionário gerado do bundle do Superset, cliente da DeepSeek, widget no Superset e testes. Correção paralela: o `scripts/dh.ps1` passou a ignorar o atalho `python` da Microsoft Store.

### 3. Usar o banco do repositório para testar

> o banco esta funcional no repos, podemos usar ele já para fazermos o teste

- **Intenção:** testar o chat contra o banco real, não contra dados de teste.
- **O que foi feito:** o warehouse estava de pé, mas o schema `gold` estava vazio. Foram carregados os 13 CSVs de `outputs/` no `gold` (dono `dh_transformer`, `SELECT` para `dh_bi_reader`), e o dashboard e o chat passaram a rodar nesses dados parciais.
- **Observação:** o pipeline completo não rodou porque não há arquivos do INEP em `data/landing`.

### 4. Aba de configurações com farol e status

> faça uma aba de configurações, onde eu tenho a section de API KEYS, nesta aba a opção inserir a api da deepseek, coloque um farol, verde para conectada e funcional, vermelha recusada e apagado vazio, deixe para para o usuario conseguir verificar o funciona, deixe tambem um modelo de sistema que eu consiga ver o o banco esta funcional

- **Intenção:** tela de administração da chave, com indicador de saúde e diagnóstico do banco.
- **O que foi feito:** seção "Chaves de API" com farol (cinza = vazio, verde = conectada e funcional, vermelho = recusada, laranja = sem como verificar) e botões *Salvar e testar*, *Testar conexão* e *Remover*; seção "Status do sistema" com conexão, prova de somente leitura, tabelas e linhas, última carga e tamanho do dicionário. O teste da chave é uma chamada real de 1 token.
- **Validação:** com uma chave deliberadamente inválida a API real respondeu 401 e o farol ficou vermelho.

### 5. Onde está o ambiente local

> onde voce subiu o local?

- **Intenção:** saber os endereços do que foi iniciado.
- **O que foi feito:** lista de containers e portas (Superset, chat, banco) e como parar e subir de novo.

### 6. Um sistema integrado, não vários links

> por que 4 links? entendo o do banco, saude, mas nao consigo entender pq esta separado o dashboard superset | dashboard | e o chat com ia?
>
> eu preciso de um sistema com tudo isto integrado, nao varios links

- **Intenção:** uma experiência única para o usuário.
- **O que foi feito:** criado o `gateway/` (nginx) que serve o Superset em `/` e o chat em `/assistente/` na porta 8088; o Superset foi movido para outra porta interna; novo comando `.\scripts\dh.ps1 app` sobe tudo. O botão do chat só aparece se o serviço estiver no ar.
- **Efeito colateral encontrado:** outra sessão estava editando `chatbot/app/db.py` e apagou a função de status do banco; foi restaurada e protegida por teste.

### 7. A configuração deve ficar em Settings

> mas onde esta esta config? nao esta em settings

- **Intenção:** encontrar a configuração no menu **Settings** do Superset, não escondida dentro do chat.
- **O que foi feito:** item *Configurações do chat (IA)* adicionado ao menu Settings (grupo Manage) via `FLASK_APP_MUTATOR`, abrindo a página `/assistente/configuracoes`.

### 8. Nada em `.env` (mensagem enviada durante a execução, com captura de tela)

> NAO QUERO NADA EM ENV, apenas no front conectado ao back, nada tem que ficar em env, para facilitar o usuario

- **Contexto:** a captura mostrava a tela "Acesso do administrador — Token de administrador inválido".
- **Intenção:** eliminar token, variáveis e arquivos que o usuário precise editar.
- **O que foi feito:** removidos o token de administrador e as variáveis `DEEPSEEK_*`/`CHAT_*` do compose, dos scripts e do `.env.example`. O acesso passou a ser pela **sessão de administrador do Superset** (o chat confere o cookie em `/api/v1/me/roles/`). A chave e o modelo (flash ou pro) são guardados no volume do chat, e o modelo também é escolhido na tela.

### 9. Login do administrador

> qual o login criado para o admin?

- **O que foi feito:** informado o usuário `admin` e o local da senha gerada (`superset/.env`, variável `SUPERSET_ADMIN_PASSWORD`).

### 10. Erro 422 no chat (com captura de tela)

> por que esta dando este erro?

- **Contexto:** a captura mostrava o chat funcionando na primeira pergunta e "Erro 422" nas seguintes.
- **Causa:** a resposta anterior do assistente (mais de 1000 caracteres) voltava no histórico e batia no limite de 1000 caracteres por mensagem.
- **Correção:** o servidor passou a aceitar respostas longas no histórico (cortadas em 1500 caracteres ao montar o contexto); pergunta do usuário continua limitada a 1000. Teste de regressão criado.

### 11. Responder tudo, para usuário leigo (com captura de tela)

> eu preciso que a ia responda tudo sobre o dashboard, o usuario nao vai perguntar corretamente, ele vai perguntar de forma leiga, pq se ele precisa usar a ia para isto, ele é leigo, entao ele nao quer pensar no que perguntar, a ia deve responder de forma direta, se o usuario quer saber sobre medicina, ele deve responder tudo sobre a medicina, sem filtro, asism como os outros

- **Contexto:** a captura mostrava a recusa padrão para "quero dados de medicina".
- **Causa:** o porteiro de escopo era rígido demais.
- **O que foi feito:** porteiro **permissivo** (na dúvida, deixa passar; só barra assunto claramente alheio, código ou tentativa de burlar regras) e novas instruções: nunca pedir para reformular, interpretar "medicina" como "tudo sobre medicina", fazer várias consultas e montar um panorama (ingressantes, desistência, pública × privada, CPC, instituições), traduzir o jargão, não narrar erros internos. Até 6 rodadas de consulta e 2000 tokens de saída.
- **Validação:** "medicina", "como está a educação?" e "engenharia" retornaram panoramas com dados; "Quem ganhou a Copa de 2022?" continuou recusado.

### 12. Estrutura da resposta e fonte dos dados

> (colou uma resposta do assistente sobre Engenharia, listando a "Fonte: gold.p2_desistencia_area, gold.p2_desistencia_curso, gold.p4_qualidade_curso, gold.p4_qualidade_faixa")
>
> a forma de resposta da ia esta boa, porem muito mal estruturada, preciso que ela responda de forma mais estruturada, se quiser use ate emojis, e tambem ela mostras as tables da onde estao sendo consultadas, isso nao pode acontecer, deve acontecer dela mostra a fonte da onde os dados foram extraidos, exemplo: ibge, inep... etc

- **Intenção:** respostas organizadas e fonte compreensível para o público.
- **Causa da bagunça:** o chat não desenhava títulos, tabelas e listas do texto gerado.
- **O que foi feito:** renderizador de Markdown no chat (títulos, citação, tabelas com cabeçalho, listas); formato fixo com emojis (título, "Em uma frase", Quadro geral, Pública × privada, Onde mais e menos se perde, Qualidade, Onde ver no dashboard, Quer ver mais?); botão ⤢ para ampliar o painel.
- **Fontes:** o servidor decide a fonte pelas tabelas realmente consultadas e mostra "📚 Fonte dos dados" com INEP (Indicadores de Trajetória, Censo, CPC, Enade) e IBGE (Censo 2022). O modelo é proibido de citar tabela, coluna, SQL ou "camada gold", e um filtro troca qualquer nome de tabela que escape pelo nome da fonte.

### 13. Gerar imagens

> preciso que o chat bot monte imagens a partir do usuario se pedir, pedi um mapa mental em imagem, e nao foi gerado, ele me monta apenas estruturas, preciso que permita ela montar apenas imagens relacionadas sobre o dashboard

- **Intenção:** o assistente deve produzir imagens de verdade (mapa mental etc.), só sobre o dashboard.
- **Causa:** o DeepSeek só gera texto; ele devolvia a estrutura em texto.
- **O que foi feito:** ferramenta `criar_imagem` (tipos `mapa_mental`, `barras`, `linhas`, `pizza`); o servidor valida e limita a especificação, e o navegador desenha em SVG com botões **⬇ Baixar PNG** e **⬇ SVG**, título, subtítulo e rodapé com a fonte pública. Pedido de imagem de outro assunto (ex.: um gato) é recusado. Máximo de 3 imagens por resposta.
- **Validação:** mapa mental de medicina e do dashboard, gráfico de barras por área e download de PNG funcionaram; os tipos linhas e pizza foram implementados e testados só por testes automáticos, não no navegador.

### 14. Esta documentação

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

- **O que foi feito:** este arquivo, com índice de prompts, intenção, resultado e decisões, mais a linha correspondente em `prompts/README.md`.

---

## Decisões de projeto que saíram dos prompts

| Decisão | Origem |
|---|---|
| Serviço próprio (FastAPI) em vez de depender do Superset | Prompt 1 |
| SQL gerado pelo modelo, mas validado no servidor (só `SELECT`, só tabelas do dashboard, `LIMIT` forçado, papel `dh_bi_reader` somente leitura) | Prompt 2 |
| Sem fine-tuning: o escopo vem de prompt, dicionário, porteiro e avaliação | Prompt 2 |
| Um só endereço para o usuário (gateway) | Prompt 6 |
| Configuração só pela interface, sem `.env` nem token; acesso por sessão de admin do Superset | Prompts 7 e 8 |
| O assistente atende leigos: responde primeiro, sem pedir para reformular | Prompt 11 |
| O usuário vê fonte pública, nunca nomes de tabelas | Prompt 12 |
| Imagens desenhadas no navegador a partir de uma especificação validada | Prompt 13 |

## O que ficou fora ou pendente

- A **bateria de avaliação** (`chatbot/tests/run_eval.py`, 15 perguntas fixas mais as de leigo e de imagem) existe, mas **não foi executada** inteira; os testes foram feitos caso a caso pelo navegador e por requisições.
- A gold usada é **parcial** (só a coorte 2020, aba B1 sem dados, sem Enade), porque o pipeline completo depende de arquivos do INEP que não estão em `data/landing`.
- Outra sessão trabalha em paralelo no "Plano B" de planilhas e em `superset/`; já houve uma sobrescrita acidental de `db.py`. O `superset/up.ps1` dela falha na primeira execução quando o Plano B está rodando.
- Imagens do tipo linhas e pizza não foram conferidas visualmente.
- A privacidade foi aceita sem aviso extra, como escolhido; as perguntas dos usuários vão para a API da DeepSeek (processamento na China).

## Arquivos principais criados ou alterados na sessão

- `chatbot/` (serviço FastAPI): `app/main.py`, `app/llm.py`, `app/prompts.py`, `app/sql_guard.py`, `app/knowledge.py`, `app/fontes.py`, `app/imagens.py`, `app/settings_store.py`, `app/deepseek_check.py`, `app/db.py`, `static/chat.html`, `static/settings.html`, `tests/`
- `gateway/` (nginx, `up.ps1`)
- `superset/chat/tail_js_custom_extra.html` (botão do chat) e `superset/superset_config.py` (item no menu Settings)
- `scripts/dh.ps1` (comando `app` e correção do atalho do Python)
- `docs/DICIONARIO_CHATBOT.md` (dicionário gerado) e `chatbot/README.md`
