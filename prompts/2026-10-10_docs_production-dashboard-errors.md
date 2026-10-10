# Sessão de 10/10/2026: erro nos tiles do dashboard em produção (Railway)

Registro de todos os prompts desta janela de contexto, na ordem, com o que foi pedido, o que foi feito e o resultado.

- **Dashboard:** https://rotadodiploma.up.railway.app/superset/dashboard/rota-do-diploma/
- **Remoto que a Railway acompanha:** `deploy` → `https://github.com/mauriciobalboa/datahack-deploy.git`, branch `main`
- **Remoto a evitar:** `origin` → `FellypeLimadaSilva/datahack` (repositório do evento)

## Resumo

| Item | Situação |
|---|---|
| Causa do erro | `ROUND(double precision, integer)` não existe no Postgres; as colunas da gold em produção são `double precision` |
| Correção no código | `ROUND(CAST(x AS NUMERIC), 1)` em `superset/build_bundle.js:147` + zip regenerado (commit `f3f56e3`) |
| Por que não apareceu em produção | O `init.sh` só importa o dashboard se ele não existir (`--if-missing`); os gráficos antigos ficam no banco do Superset |
| Solução do reimport | `FORCE_REIMPORT=1` aciona `reimport.py --force` no boot (commit `a291fb1`) |
| Estado na última checagem | Gráficos 50, 51, 53 e 58 ainda com a consulta antiga; reimport não confirmado |
| Dado vazio, à parte | `gold.b1_desertos_municipio` sem linhas (tile "Municípios" mostra "— de 0") |

## Prompts

### 1. Relato do erro

> analise, deu erros no link de prod

Enviados junto: o link do dashboard, uma captura de tela da aba "Visão geral" (três tiles com "Unexpected error") e o log do console colado quatro vezes, com o mesmo conteúdo. O log trazia avisos do Superset (`Duplicate translation key`, `antd`) e quatro respostas 400 em `/api/v1/chart/data` para os slices 50, 51, 58 e 53.

**O que foi feito**
- Abri o dashboard no navegador do app e li a resposta real do Postgres via API.
- Todos os 58 gráficos estão sem `query_context`, então o front-end monta o POST sozinho.
- Reproduzi a consulta do gráfico 50 e o Postgres respondeu `function round(double precision, integer) does not exist`.
- Localizei a origem em `superset/build_bundle.js:147` (`txt = e => REPLACE(CAST(ROUND(e, 1) AS TEXT), ...)`).
- Corrigi para `ROUND(CAST(e AS NUMERIC), 1)`, regenerei `superset/bundle/rota_do_diploma.zip` (58 gráficos, 13 datasets, 9 abas, 19 filtros) e validei as quatro métricas contra a produção: todas retornaram 200.
- Encontrei também que `gold.b1_desertos_municipio` está vazia em produção (CSV de 133 bytes, só cabeçalho).

**Resultado:** diagnóstico e correção local prontos; commit e push pendentes de autorização.

### 2. Autorização para publicar

> se for corrigir, pode fazer

**O que foi feito**
- Commit `f3f56e3` na branch local `deploy`.
- Por engano, o push foi para `origin` (repositório do evento), criando a branch `deploy` lá.
- A exclusão dessa branch e um `git fetch` foram negados pelo classificador de permissões; não contornei e passei os comandos para o usuário rodar.

**Resultado:** correção commitada, publicada no remoto errado e ainda não no certo.

### 3. Falha no cmd

> no cmd retornou falha, faço no git?

**O que foi feito:** tentei ler o terminal do app (estava vazio, o usuário usou outro cmd). Expliquei que o que importa é a mensagem do erro e listei as causas mais comuns.

### 4. Captura do erro (`oring`)

Captura de tela do cmd com `git push oring --delete deploy` e a resposta `'oring' does not appear to be a git repository`.

**O que foi feito:** apontei o erro de digitação (`oring` em vez de `origin`) e dei o comando correto, mais a sequência `git fetch deploy` → `git rev-list --left-right --count HEAD...deploy/main` → `git push deploy deploy:main`.

### 5. Branch removida do repositório do evento

Saída colada: `git push origin --delete deploy` com `- [deleted] deploy`.

**Resultado:** a branch criada por engano no repositório do evento foi apagada.

### 6. Comparação com o remoto da Railway

Saída colada: `git fetch deploy` e `git rev-list ... → 1 0`.

**Resultado:** a branch local estava um commit à frente e o remoto não tinha nada além dela, então o `git push deploy deploy:main` era seguro.

### 7. Deploy em andamento

Captura de tela da Railway mostrando o serviço `superset` em "Deploying (03:40)".

**O que foi feito:** verifiquei a produção: os quatro gráficos ainda estavam com a consulta antiga, e expliquei que o import do dashboard só ocorre no fim da subida do Superset.

### 8. Pedido de verificação e do link

> verifique para mim se esta certo agora, e preciso que voce me envie o link novamente, nao consegui localizar

**O que foi feito**
- Verifiquei de novo: ainda a versão antiga.
- Confirmei que `deploy/main` já continha `f3f56e3`.
- Descobri o motivo: `superset/docker/init.sh` roda `reimport.py --if-missing`, que não atualiza gráficos existentes.
- Alterei o `init.sh` para aceitar `FORCE_REIMPORT=1` (usa `--force`), com checagem de sintaxe, e fiz o commit `a291fb1`.
- Reenviei o link do dashboard e os três passos pendentes: push do novo commit, criar a variável na Railway, remover a variável depois.

### 9. Nova verificação

> confira

**Resultado:** gráficos 50, 51, 53 e 58 ainda sem `AS NUMERIC`; nenhum reimport tinha rodado. Pedi para conferir push, variável e log de deploy.

### 10. Confirmação do push

Saída colada: `git log --oneline deploy/main -1` → `a291fb1 ... (deploy/main, deploy/HEAD)`.

**Resultado:** o commit com `FORCE_REIMPORT` está no remoto da Railway. O reimport continuava sem aparecer: faltava a variável criada antes do deploy.

### 11. Acesso à CLI

> voce tem acesso a cli, confere para mim, estou resolvendo problema do bd

**O que foi feito:** procurei `railway` no Git Bash e no PowerShell e não está instalado. Sem a CLI, a checagem só é possível pelo resultado em produção.

### 12. Build concluído

> o build da railway ja saiu, confere se o sistema ja esta atualizado

**Resultado:** ainda não atualizado. Três tiles de percentual seguiam com "Unexpected error" (Ingressantes e os gráficos de barras carregavam) e os quatro gráficos continuavam com a consulta antiga. Hipóteses: variável ausente ou import falhando.

### 13. Relação com o banco

> o banco esta com uma falha, porem no local host ja é de forma diferente como esta em prod, o motivo do erro em prod pode ser o por causa do banco?

**O que foi feito:** comparei o código. Localmente o dbt gera colunas `::numeric`; em produção o `load_gold.py` usa `pandas.to_sql`, que grava `double precision`. A origem do erro é essa diferença de tipo, não falha do banco. O `CAST ... AS NUMERIC` resolve nos dois ambientes.

### 14. Contexto para outro chat

> me passa um contexto do erro da railway, o banco ja foi corrigido, entao foque so na falha do erro da railway para eu usar em outro chat

**O que foi feito:** entreguei um texto de contexto com sintoma, causa, correção, o motivo de o dashboard não atualizar, a lista do que verificar na Railway, um trecho de JavaScript para conferir pelo navegador e o aviso sobre `origin` versus `deploy`.

### 15. Esta documentação

> faça uma documentação sobre todos meus prompts em .md desta janela de contexto

**O que foi feito:** este arquivo.

## Pendências

1. Na Railway, serviço `superset`: criar `FORCE_REIMPORT=1`, aguardar o deploy e confirmar no log a linha `>> FORCE_REIMPORT=1: reimportando o dashboard do zero`, sem `IMPORTACAO FALHOU` depois.
2. Conferir pelo navegador que os gráficos 50, 51, 53 e 58 passaram a conter `AS NUMERIC` e que os tiles carregam.
3. **Remover `FORCE_REIMPORT` depois**, senão todo deploy apaga e recria o dashboard (e os ids dos gráficos mudam).
4. Resolver a carga de `b1_desertos_municipio` no pipeline para o tile "Municípios".
5. O arquivo `chatbot/app/settings_store.py` aparece como deletado no `git status` desde antes desta sessão e ficou fora dos commits.

## Comandos usados no fluxo

```bash
git push origin --delete deploy        # limpeza da branch criada por engano no repo do evento
git fetch deploy
git rev-list --left-right --count HEAD...deploy/main
git push deploy deploy:main            # publicação que a Railway acompanha
git log --oneline deploy/main -1
```

Atenção: `origin` é o repositório do evento e não deve receber pushes deste trabalho.
