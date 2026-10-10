# Chat com IA do dashboard (DeepSeek)

Botão flutuante **"Pergunte aos dados"** nas páginas de dashboard do Superset. O assistente só responde sobre o que o
dashboard mostra e busca números na camada gold com o papel somente leitura `dh_bi_reader`.

```
Superset (8088) ── botão + iframe ──► chatbot (8099) ──► DeepSeek API
                                          └──► warehouse (schema gold, dh_bi_reader)
```

## Endereço único

**http://localhost:8088** é o sistema inteiro: abre direto no dashboard, e o chat (botão **Pergunte aos dados**) e a página de
configurações saem pelo mesmo endereço, em `/assistente/`. Quem faz isso é o `gateway/` (nginx). As demais portas
(Superset em 8090, chat em 8099, banco em 5433) são internas e só servem para diagnóstico; não são links de uso.

```powershell
.\scripts\dh.ps1 app      # sobe banco + Superset + chat + gateway e mostra o endereço único
```

## Configurar a chave da DeepSeek (sem .env, sem token)

1. Em http://localhost:8088 clique em **Login** e entre no Superset como `admin`.
2. Abra **Settings > Manage > Configurações do chat (IA)** (só administradores veem esse item).
3. Cole a chave (platform.deepseek.com/api_keys), clique em **Salvar e testar** e veja o farol.

Nada vai para `.env`, `docker-compose` ou Git: o serviço guarda a chave no volume `chatbot-data` e o modelo (flash ou pro) também é escolhido nessa tela.
Sem chave o `/chat` responde 503 e o resto funciona normalmente.

## Subir por partes

1. `scripts\dh.ps1 up-lite` e `scripts\dh.ps1 pipeline` (warehouse com a gold), depois `superset\up.ps1`.
2. `chatbot\up.ps1`, depois `gateway\up.ps1` (libera a 8088 e junta tudo no endereço único).

## Página Configurações do chat (IA)

| Bloco | O que mostra |
|---|---|
| **Chaves de API · DeepSeek** | Farol: **cinza** = vazio · **verde** = conectada e funcional · **vermelho** = recusada (401, sem saldo ou modelo recusado) · **laranja** = não deu para verificar (rede). Escolha do modelo e botões *Salvar e testar*, *Testar conexão* e *Remover chave* |
| **Status do sistema** | Farol geral do banco; conexão (latência, papel, versão); prova de **somente leitura** (tenta criar uma tabela e é barrado); existência e linhas das 13 tabelas gold; última carga; tamanho do dicionário |

- O teste da chave é uma chamada real de 1 token ao modelo (custo desprezível), não só uma checagem de formato.
- A chave é gravada no volume `chatbot-data` (`/data/settings.json`, modo 600) e **nunca volta ao navegador**: a API só devolve `sk-…1234`.
- **Quem pode abrir:** só sessão de administrador do Superset. O serviço repassa o cookie do navegador ao Superset (`/api/v1/me/roles/`) e exige o papel `Admin`; visitante do dashboard recebe 401. O item do menu vem de `FLASK_APP_MUTATOR` em `superset/superset_config.py`.

## Como o assistente é limitado ao dashboard ("treino")

A DeepSeek não tem fine-tuning na API oficial, e ele não imporia escopo. O controle é por contexto e ferramentas:

| Camada | Onde | O que faz |
|---|---|---|
| Porteiro de escopo | `app/llm.py` `in_scope` | Regex de injeção + uma chamada curta (SIM/NAO); fora do tema → recusa padrão |
| System prompt | `app/prompts.py` | Papel, escopo, regras de interpretação (taxa ponderada, células pequenas, evasão ≠ desistência), citar fonte |
| Dicionário de dados | `app/knowledge.py` | Gerado do bundle do Superset + `outputs/_indicadores.json` (`docs/DICIONARIO_CHATBOT.md`). Não é escrito à mão |
| SQL validado | `app/sql_guard.py` | Só um SELECT, só tabelas do dashboard (13), schema gold, funções perigosas barradas, `LIMIT 200` |
| Banco | `app/db.py` | `dh_bi_reader`: transação read-only, `statement_timeout` de 10 s |
| Limites | `app/main.py` | 10 req/min por IP, teto diário (`CHAT_DAILY_CAP`), 8 mensagens de histórico, 1000 caracteres |

A segurança real fica no servidor (guard + papel read-only), não no prompt: assuma que o prompt pode vazar.

## Testes

```powershell
# unitários do SQL guard (sem chave, sem banco)
docker build -t rota-chatbot chatbot; docker run --rm rota-chatbot python -m pytest tests -q
# bateria de avaliação (precisa do serviço no ar com a chave real; ~15 perguntas)
docker compose -f chatbot/docker-compose.yml exec chatbot python tests/run_eval.py
```

Rode a bateria a cada mudança de prompt ou de modelo. Para atualizar o dicionário depois de mudar o dashboard:
`python -m app.knowledge` dentro do container (veja o cabeçalho de `docs/DICIONARIO_CHATBOT.md`) e reinicie o serviço.

## Privacidade e custo

- A DeepSeek processa dados na China. Vão para a API: o dicionário, as perguntas e os resultados agregados das consultas (gold é agregada, sem microdados). A chave fica só no servidor.
- Modelo `deepseek-flash`, sem modo thinking; o prefixo fixo (prompt + dicionário, ~10 mil tokens) entra no cache automático da DeepSeek.
- `deepseek-chat` e `deepseek-reasoner` foram aposentados; escolha o modelo na página de configurações (flash ou v4-pro).

## Limitações conhecidas

- O contexto de filtros vem da API do Superset (`filter_state`); se o acesso anônimo não puder lê-la, o assistente fica só com a aba ativa.
- Dados parciais na gold (Enade, IBGE) aparecem vazios; o assistente deve avisar em vez de inventar.

## Plano B: o chat lendo planilhas (sem banco)

Quando o dashboard roda sem o warehouse (`superset\up.ps1 -Planilhas` ou `scripts\dh.ps1 planilhas`), o chat passa a ler o mesmo SQLite
que o Superset monta a partir das planilhas. O `up.ps1` do Superset já troca o chat junto (se ele já foi criado antes); na mão:

```powershell
cd chatbot
docker compose -f docker-compose.yml -f docker-compose.planilhas.yml up -d --build    # Plano B
docker compose up -d --build                                                          # volta ao warehouse
```

`DATA_SOURCE=planilhas` muda três coisas: o SQL é validado e executado como **SQLite** (`sql_guard.py` tira o `gold.` do dicionário e barra
`ATTACH`, `PRAGMA`, `load_extension`...), o prompt avisa o dialeto (booleanos são 0/1) e `db.py` abre o arquivo só para leitura, com
autorizador que só aceita `SELECT`. O escopo, o porteiro e os limites são os mesmos.
