# Montar o ambiente no laboratório (sábado, 08:00–08:45)

Meta: em até 30 minutos, Postgres no ar, ingestão e dbt funcionando, sem depender do Airflow.

## Hoje à noite (no seu PC)

1. `git push origin main` e confira na aba **Actions** do GitHub que os jobs **Fluxo do laboratório em
   Docker** e **Build da imagem** ficaram verdes. É a prova de que o Docker sobe do zero.
2. Pendrive (plano contra rede lenta), com Docker Desktop instalado e aberto no seu PC:

   ```powershell
   .\scripts\dh.ps1 up-lite        # baixa o Postgres e constrói a imagem CLI
   .\scripts\dh.ps1 images-save    # gera images\datahack-images.tar
   ```

   Copie para o pendrive: a pasta do repositório (sem `data/`), o `images\datahack-images.tar` e o
   instalador do Docker Desktop (`Docker Desktop Installer.exe`).

## No laboratório

| Passo | Comando | Tempo |
|---|---|---|
| 1. Docker Desktop aberto, mostrando "Engine running" | — | 1–3 min |
| 2. Clonar | `git clone https://github.com/FellypeLimadaSilva/datahack.git; cd datahack` | 1 min |
| 3. Diagnóstico | `.\scripts\dh.ps1 doctor` | 10 s |
| 4. Imagens do pendrive (se a rede estiver lenta) | copie o `.tar` para `images\` e rode `.\scripts\dh.ps1 images-load` | 2–4 min |
| 5. Subir | `.\scripts\dh.ps1 up-lite` | 1 min com imagens, 5–8 min sem |
| 6. Testar | `.\scripts\dh.ps1 smoke` | 30 s |
| 7. Dados | baixar das fontes do evento para `data\landing\inbox\` (veja `docs/estrategia.md`) | rede |
| 8. Rodar | `.\scripts\dh.ps1 discover` e depois `.\scripts\dh.ps1 pipeline` | minutos |

`up-lite` sobe só o Postgres e a imagem CLI (cerca de 2 GB de RAM). O Airflow é opcional: se a máquina
tiver 8 GB ou mais e der tempo, `.\scripts\dh.ps1 up` sobe a plataforma completa.

Se o PowerShell bloquear o script: `Set-ExecutionPolicy -Scope Process Bypass` na mesma janela.

## Problemas comuns

| Sintoma no `doctor` ou na subida | Ação |
|---|---|
| Docker CLI ausente | Instalar o Docker Desktop do pendrive (exige administrador) |
| Docker Engine falha | Abrir o Docker Desktop e esperar; se pedir WSL: `wsl --install` como administrador e reiniciar |
| "Virtualization not enabled" | Não dá para resolver sem BIOS: use o plano sem Docker abaixo |
| Porta 5433 em uso | Trocar `WAREHOUSE_PORT` no `.env` e rodar de novo |
| Fim de linha dos scripts | `git config --global core.autocrlf false` e clonar de novo |
| Download de imagem lento ou bloqueado | `images-load` com o `.tar` do pendrive |
| Disco com menos de 10 GB | Liberar espaço; o Censo 2024 sozinho ocupa ~1 GB no banco |
| Máquina com congelamento (reinicia limpa) | Não reiniciar; o banco fica no volume do Docker |

## Plano sem Docker

Requer PostgreSQL 16 instalado (instalador oficial, com `psql` no PATH) e Python 3.12.

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\scripts\dh.ps1 env
```

No `.env`: `WAREHOUSE_HOST=localhost` e `WAREHOUSE_PORT=5432` (porta do instalador). Depois:

```powershell
.\scripts\dh.ps1 db-bootstrap-native      # pede a senha do usuario postgres
$env:DH_RUNNER = "native"
.\scripts\dh.ps1 smoke
.\scripts\dh.ps1 pipeline
```

Todos os comandos do `dh.ps1` funcionam iguais nesse modo, só que rodando no Python local.

## Reprodutibilidade (para o README da equipe)

Do zero, em qualquer máquina com Docker:

```powershell
git clone <repositório>; cd <repositório>
.\scripts\dh.ps1 up-lite
# baixar as bases para data\landing\inbox\ (links no README)
.\scripts\dh.ps1 pipeline
```

O resultado fica em `outputs/` (CSV e Parquet, com `_manifest.json` contendo linhas e hash de cada
arquivo): quem reproduzir confere se chegou aos mesmos números comparando os hashes.
