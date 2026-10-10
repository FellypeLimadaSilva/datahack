# Plano B · o dashboard sem banco de dados

Se o Postgres (warehouse) falhar, o **mesmo dashboard** (9 abas, 54 gráficos, filtros e chat) roda lendo **planilhas**.
Nada de banco: as planilhas viram um arquivo SQLite local, dentro do container do Superset, e o painel lê dali.

## Em 3 passos

1. Suba o Plano B (só precisa do Docker aberto):
   ```powershell
   cd superset
   powershell -ExecutionPolicy Bypass -File .\up.ps1 -Planilhas
   ```
2. Abra **http://localhost:8088** (leitura sem login; edição: usuário `admin` e a senha que o comando imprime).
3. **Solte as planilhas nesta pasta** (`superset/planilhas/`). Em ~10 segundos o painel recarrega sozinho; basta atualizar a página.

Se a pasta estiver vazia, o painel usa as exportações da Gold que já estão em `outputs/` (CSV/Parquet). Ou seja:
**funciona mesmo sem você fazer nada**, com os últimos números publicados.

## Quais arquivos servem

| Tipo | Extensões |
|---|---|
| Texto delimitado | `.csv` `.tsv` `.txt` `.tab` `.psv` `.dat` (vírgula, ponto e vírgula, tab ou barra vertical: detecta sozinho) |
| Excel / LibreOffice | `.xlsx` `.xlsm` `.xltx` `.xltm` `.xls` `.xlsb` `.ods` |
| Colunar | `.parquet` |
| JSON | `.json` (lista de objetos, ou `{"aba": [..]}`) · `.jsonl` `.ndjson` |
| Compactados | `.zip` `.gz` `.bz2` `.xz` com qualquer um dos acima dentro |

O formato é reconhecido pelo **conteúdo**, não só pela extensão (um `.xls` que na verdade é CSV abre normalmente).
Ignorados de propósito: arquivos que começam com `_` ou `~$` (rascunhos e travas do Excel) e pastas que começam com `_`.

## Qual planilha vira qual tabela

O dashboard tem **13 tabelas** (lista e colunas em [CONTRATO.md](CONTRATO.md)). O carregador descobre, nesta ordem:

1. **Pelo nome** do arquivo ou da aba: `p1_trajetoria_coorte.csv`, aba `p2_desistencia_area`, ou só o código quando não
   há dúvida (`p1`, `p3`, `b1`; `p2`, `p4`, `p5` e `b2` têm mais de uma tabela, então use o nome completo).
2. **Pelas colunas**, se o nome não ajudar: um arquivo `dados_final_v3.xlsx` com o cabeçalho de `p3_rede_modalidade_ano` é
   reconhecido como essa tabela.
3. Uma pasta de trabalho pode ter **várias abas**, cada uma de uma tabela. Abas que não casam com nada são ignoradas.

Dentro da planilha:

- O **cabeçalho** pode estar em qualquer uma das primeiras 30 linhas (títulos e logos acima da tabela não atrapalham).
- Nomes de coluna **sem distinção** de maiúsculas, acentos e espaços (`Taxa Desistência Marco` = `taxa_desistencia_marco`).
  Os rótulos do dashboard (`Coorte (ano de ingresso)`) também valem.
- **Números**: ponto ou vírgula decimal, `1.234,5`, `23,4%`, `R$ 10,00`. Vazio, `--`, `SC`, `NA`, `-` = sem dado (não é zero).
- **Verdadeiro/falso**: `true/false`, `sim/não`, `1/0`, `verdadeiro/falso`.
- Colunas que faltam ficam vazias; colunas a mais são ignoradas. Os avisos aparecem no relatório.
- Se houver **mais de uma planilha** para a mesma tabela, vale a mais recente (CSV e Parquet do mesmo export são tratados como um só).
- Planilha da equipe + Gold exportada ao mesmo tempo: a planilha vence, tabela por tabela.
- Se não houver planilha de `controle_atualizacao`, ela é gerada a partir dos arquivos carregados (fonte = tabela, data = agora).

Uma pasta de trabalho em branco, com uma aba por tabela e a lista de colunas:

```powershell
docker compose -f superset/docker-compose.planilhas.yml exec superset python /app/planilhas.py --modelo /planilhas/_modelo.xlsx
```

## Conferir o que foi lido

```powershell
docker compose -f superset/docker-compose.planilhas.yml exec superset python /app/planilhas.py --check
```

Mostra, por tabela, quantas linhas vieram, de qual arquivo/aba, e os avisos (colunas ausentes, valores inválidos,
cabeçalho achado na linha N, arquivos que não foram reconhecidos). `--check` não grava nada. O mesmo relatório sai nos
logs (`docker compose -f superset/docker-compose.planilhas.yml logs -f superset`) a cada recarga.

Recarregar na hora, sem esperar os ~10 s: rode o comando sem `--check`.

## Voltar ao modo normal (com o banco)

```powershell
cd superset
powershell -ExecutionPolicy Bypass -File .\up.ps1
```

Os dois modos nunca rodam juntos (usam a mesma porta 8088); cada um guarda seus próprios dados.

## Limites a ter em mente

- O painel mostra o que **a planilha** diz. O Plano B não recalcula nada: as taxas, os cortes de células pequenas (< 10 alunos) e
  os rankings (30+ ingressantes) já vêm prontos da Gold. Se a planilha for montada à mão, essas regras são de quem montou.
- O chat com IA também lê as planilhas (veja `chatbot/README.md`), mas só se o serviço estiver no ar.
- Se uma linha tiver valor não numérico numa coluna numérica, ele vira vazio e o relatório avisa quantos e quais.
