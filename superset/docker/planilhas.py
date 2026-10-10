"""Plano B sem banco de dados: carrega planilhas num SQLite que o Superset lê no lugar do warehouse.

  python /app/planilhas.py                 carrega e troca o SQLite (atômico: se falhar, o anterior continua)
  python /app/planilhas.py --check         só confere e mostra o relatório, sem gravar
  python /app/planilhas.py --watch [seg]   recarrega sozinho quando algo muda nas pastas (padrão: a cada 5 s)
  python /app/planilhas.py --modelo X.xlsx gera uma pasta de trabalho em branco com uma aba por tabela

Onde procura (nesta ordem; a primeira que tiver linhas vence, por tabela):
  1. PLANILHAS_DIR   (padrão /planilhas)  o que a equipe soltar ali
  2. FALLBACK_DIR    (padrão /outputs)    as exportações da Gold (CSV/Parquet) que o pipeline já gera

Formatos: csv tsv txt tab psv dat · xlsx xlsm xltx xltm xls xlsb ods · parquet · json jsonl ndjson ·
e qualquer um deles dentro de .zip .gz .bz2 .xz. O formato é reconhecido pelo conteúdo, não só pela extensão
(um .xls que na verdade é CSV ou xlsx também abre).

Qual planilha é qual tabela: pelo nome do arquivo ou da aba (p1_trajetoria_coorte.csv, aba "P2 desistencia area",
ou só "p1"); se o nome não ajudar, pelas colunas (cabeçalho igual ao de uma tabela do contrato).
O contrato de colunas vem de /bundle/contrato_planilhas.json, gerado por build_bundle.js.
"""
from __future__ import annotations

import argparse
import bz2
import csv
import datetime as dt
import gzip
import io
import json
import lzma
import os
import re
import sqlite3
import sys
import time
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

CONTRATO = Path(os.environ.get("PLANILHAS_CONTRATO", "/bundle/contrato_planilhas.json"))
PASTA = Path(os.environ.get("PLANILHAS_DIR", "/planilhas"))
FALLBACK = Path(os.environ.get("FALLBACK_DIR", "/outputs"))
DB_PATH = Path(os.environ.get("PLANILHAS_DB", "/app/superset_home/planilhas.db"))
RELATORIO = Path(os.environ.get("PLANILHAS_RELATORIO", str(DB_PATH.with_suffix(".relatorio.json"))))

TEXTO = {".csv", ".tsv", ".txt", ".tab", ".psv", ".dat"}
EXCEL = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls", ".xlsb", ".ods"}
OUTROS = {".parquet", ".json", ".jsonl", ".ndjson"}
COMPACTADO = {".zip", ".gz", ".bz2", ".xz"}
SUPORTADOS = TEXTO | EXCEL | OUTROS | COMPACTADO
NULOS = {"", "na", "n/a", "nan", "null", "none", "nil", "-", "--", "---", "—", "–", "s/d", "sc", "s/c", "nd", "n/d", "n.d.",
         "#n/a", "#n/d", "#div/0!", "#valor!", "#value!", "#ref!", "..", "...", "*"}
VERDADEIRO = {"true", "t", "1", "1.0", "sim", "s", "verdadeiro", "v", "yes", "y"}
FALSO = {"false", "f", "0", "0.0", "nao", "n", "falso", "no"}
LINHAS_PARA_CABECALHO = 30        # procura o cabeçalho nas primeiras linhas (títulos acima da tabela são comuns)
SOBREPOSICAO_MIN = 0.6            # fração das colunas esperadas para reconhecer uma tabela só pelas colunas


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


@dataclass
class Tabela:
    nome: str
    descricao: str
    colunas: list[dict]
    alias: dict[str, str] = field(default_factory=dict)      # nome normalizado -> coluna

    def __post_init__(self):
        for c in self.colunas:
            self.alias[norm(c["nome"])] = c["nome"]
        for c in self.colunas:                               # rótulos do dashboard também valem como cabeçalho
            if c.get("rotulo"):
                self.alias.setdefault(norm(c["rotulo"]), c["nome"])


def carregar_contrato() -> dict[str, Tabela]:
    if not CONTRATO.exists():
        raise SystemExit(f"ERRO: contrato não encontrado em {CONTRATO}. Rode: node superset/build_bundle.js")
    dados = json.loads(CONTRATO.read_text(encoding="utf-8"))
    return {k: Tabela(k, v["descricao"], v["colunas"]) for k, v in dados["tabelas"].items()}


# ───────────────────────── leitura: tudo vira "linhas de texto" ─────────────────────────
Linhas = list[list]            # linhas de células (str ou None)


def _decodificar(dados: bytes) -> str:
    if dados[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return dados.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):                    # Excel em português salva CSV em cp1252
        try:
            return dados.decode(enc)
        except UnicodeDecodeError:
            continue
    return dados.decode("latin-1")


def _ler_texto(dados: bytes, ext: str) -> Linhas:
    texto = _decodificar(dados)
    amostra = "\n".join(texto.splitlines()[:50])
    if ext == ".tsv" or ext == ".tab":
        sep = "\t"
    elif ext == ".psv":
        sep = "|"
    else:
        cont = {s: amostra.count(s) for s in (",", ";", "\t", "|")}
        sep = max(cont, key=cont.get) if max(cont.values()) else ","
    linhas = [[(c if c != "" else None) for c in row] for row in csv.reader(io.StringIO(texto), delimiter=sep)]
    return [r for r in linhas if any(c is not None for c in r)]


def _df_para_linhas(df) -> Linhas:
    import pandas as pd
    df = df.astype(object).where(df.notna(), None)
    cab = [str(c) for c in df.columns]
    corpo = [[None if v is None else (v.isoformat() if isinstance(v, (dt.datetime, dt.date, pd.Timestamp)) else str(v)) for v in row]
             for row in df.itertuples(index=False, name=None)]
    return [cab] + corpo


def _motor_excel(dados: bytes, ext: str) -> str | None:
    if dados[:4] == b"PK\x03\x04":
        return "odf" if ext == ".ods" else ("pyxlsb" if ext == ".xlsb" else "openpyxl")
    if dados[:4] == b"\xd0\xcf\x11\xe0":
        return "xlrd"
    return None


def _ler_excel(dados: bytes, ext: str) -> list[tuple[str, Linhas]]:
    import pandas as pd
    motor = _motor_excel(dados, ext)
    if motor is None:                                  # "xls" que é CSV disfarçado (alguns sistemas exportam assim)
        if dados.lstrip()[:1] == b"<":
            raise ValueError("é HTML com extensão de planilha; abra no Excel e salve como .xlsx ou .csv")
        return [("", _ler_texto(dados, ".csv"))]
    abas = pd.read_excel(io.BytesIO(dados), sheet_name=None, header=None, dtype=str, engine=motor, keep_default_na=False)
    saida = []
    for nome, df in abas.items():
        df = df.astype(object).where(df.notna(), None)
        linhas = [[(None if v is None or str(v) == "" else str(v)) for v in row] for row in df.itertuples(index=False, name=None)]
        saida.append((str(nome), [r for r in linhas if any(c is not None for c in r)]))
    return saida


def _ler_json(dados: bytes, ext: str) -> list[tuple[str, Linhas]]:
    import pandas as pd
    texto = _decodificar(dados)
    if ext in (".jsonl", ".ndjson"):
        return [("", _df_para_linhas(pd.read_json(io.StringIO(texto), lines=True, dtype=False)))]
    obj = json.loads(texto)
    if isinstance(obj, dict) and obj and all(isinstance(v, list) for v in obj.values()):
        return [(k, _df_para_linhas(pd.DataFrame(v))) for k, v in obj.items()]
    if isinstance(obj, dict):
        for chave in ("data", "dados", "rows", "linhas", "records", "items"):
            if isinstance(obj.get(chave), list):
                obj = obj[chave]
                break
    return [("", _df_para_linhas(pd.DataFrame(obj)))]


def abrir(nome: str, dados: bytes) -> list[tuple[str, Linhas]]:
    """Devolve [(rótulo da aba/arquivo interno, linhas)] para qualquer formato aceito."""
    ext = Path(nome).suffix.lower()
    if ext == ".zip":
        saida = []
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            for info in z.infolist():
                interno = Path(info.filename)
                if info.is_dir() or interno.name.startswith(("~$", "._", "_")) or "__MACOSX" in interno.parts:
                    continue
                if interno.suffix.lower() in SUPORTADOS:
                    for rot, linhas in abrir(interno.name, z.read(info)):
                        saida.append((f"{interno.name}{'#' + rot if rot else ''}", linhas))
        return saida
    if ext in (".gz", ".bz2", ".xz"):
        raw = {".gz": gzip.decompress, ".bz2": bz2.decompress, ".xz": lzma.decompress}[ext](dados)
        return abrir(Path(nome).stem, raw)
    if ext in EXCEL:
        return _ler_excel(dados, ext)
    if ext == ".parquet":
        import pandas as pd
        return [("", _df_para_linhas(pd.read_parquet(io.BytesIO(dados))))]
    if ext in (".json", ".jsonl", ".ndjson"):
        return _ler_json(dados, ext)
    if ext in TEXTO:
        return [("", _ler_texto(dados, ext))]
    return []


# ───────────────────────── reconhecer cabeçalho e tabela ─────────────────────────
def sobreposicao(celulas: list, t: Tabela) -> float:
    achados = {t.alias[n] for n in (norm(c) for c in celulas if c is not None) if n in t.alias}
    return len(achados) / len(t.colunas)


def melhor_cabecalho(linhas: Linhas, t: Tabela) -> tuple[int, float]:
    melhor = (0, 0.0)
    for i, row in enumerate(linhas[:LINHAS_PARA_CABECALHO]):
        s = sobreposicao(row, t)
        if s > melhor[1]:
            melhor = (i, s)
    return melhor


def tabela_pelo_nome(rotulo: str, tabelas: dict[str, Tabela]) -> Tabela | None:
    n = norm(rotulo)
    if not n:
        return None
    if n in tabelas:
        return tabelas[n]
    contidas = [t for t in tabelas if t in n]
    if contidas:
        return tabelas[max(contidas, key=len)]
    partes = n.split("_")                                    # "p1 trajetória", "gold p3 rede": código + 1ª palavra
    parciais = [t for t in tabelas if all(p in partes for p in t.split("_")[:2])]
    if len(parciais) == 1:
        return tabelas[parciais[0]]
    codigos: dict[str, list[str]] = {}
    for t in tabelas:
        codigos.setdefault(t.split("_")[0], []).append(t)
    for p in n.split("_"):
        if p in codigos and len(codigos[p]) == 1:           # "p1", "b1": só vale se não houver ambiguidade
            return tabelas[codigos[p][0]]
    return None


def tabela_pelas_colunas(linhas: Linhas, tabelas: dict[str, Tabela]) -> tuple[Tabela | None, int, float]:
    ranking = []
    for t in tabelas.values():
        i, s = melhor_cabecalho(linhas, t)
        ranking.append((s, t, i))
    ranking.sort(key=lambda x: -x[0])
    if not ranking or ranking[0][0] < SOBREPOSICAO_MIN:
        return None, 0, 0.0
    if len(ranking) > 1 and ranking[0][0] - ranking[1][0] < 0.05 and ranking[1][0] >= SOBREPOSICAO_MIN:
        return None, 0, ranking[0][0]                        # empate: não adivinha
    return ranking[0][1], ranking[0][2], ranking[0][0]


# ───────────────────────── conversão de valores ─────────────────────────
RUIM = object()


def numero(s, inteiro: bool):
    if s is None:
        return None
    t = str(s).strip().replace(" ", "").replace(" ", "").replace("−", "-")
    if t.lower() in NULOS:
        return None
    t = t.replace("%", "").replace("R$", "")
    neg = t.startswith("(") and t.endswith(")")
    if neg:
        t = t[1:-1]
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        if t.count(",") > 1 or (inteiro and re.fullmatch(r"-?\d{1,3},\d{3}", t)):
            t = t.replace(",", "")                           # 1,234,567 ou 1,234 numa coluna de inteiros
        else:
            t = t.replace(",", ".")                          # vírgula decimal (pt-BR)
    elif t.count(".") > 1 or (inteiro and re.fullmatch(r"-?\d{1,3}\.\d{3}", t)):
        t = t.replace(".", "")                               # 1.234.567 ou 1.234 numa coluna de inteiros
    try:
        v = float(t)
    except ValueError:
        return RUIM
    v = -v if neg else v
    if v != v or v in (float("inf"), float("-inf")):
        return RUIM
    return int(round(v)) if inteiro else v


def booleano(s):
    if s is None:
        return None
    t = norm(s)
    if t in VERDADEIRO:
        return 1
    if t in FALSO:
        return 0
    return None if t in NULOS or t == "" else RUIM


def texto(s):
    if s is None:
        return None
    t = str(s).strip()
    return None if t == "" else t


# ───────────────────────── montar uma tabela a partir das linhas ─────────────────────────
@dataclass
class Carga:
    tabela: Tabela
    origem: str
    linhas: list[tuple]
    avisos: list[str]
    mtime: float


def converter(t: Tabela, linhas: Linhas, i_cab: int, origem: str, mtime: float) -> Carga:
    cab = linhas[i_cab]
    posicao: dict[str, int] = {}
    ignoradas = []
    for j, c in enumerate(cab):
        if c is None or str(c).strip() == "":
            continue
        alvo = t.alias.get(norm(c))
        if alvo and alvo not in posicao:
            posicao[alvo] = j
        elif not alvo:
            ignoradas.append(str(c))
    avisos = []
    faltando = [c["nome"] for c in t.colunas if c["nome"] not in posicao]
    if faltando:
        avisos.append(f"colunas ausentes (ficam vazias): {', '.join(faltando)}")
    if ignoradas:
        avisos.append(f"colunas que o dashboard não usa (ignoradas): {', '.join(ignoradas[:8])}{'…' if len(ignoradas) > 8 else ''}")

    corpo = linhas[i_cab + 1:]
    colunas = []
    ruins: dict[str, list] = {}
    for c in t.colunas:
        j = posicao.get(c["nome"])
        bruto = [(r[j] if j is not None and j < len(r) else None) for r in corpo]
        tipo = c["tipo"]
        if tipo == "BIGINT" or tipo == "NUMERIC":
            conv = [numero(v, tipo == "BIGINT") for v in bruto]
        elif tipo == "BOOLEAN":
            conv = [booleano(v) for v in bruto]
        else:
            conv = [texto(v) for v in bruto]
            # código que o Excel guardou como número (4.0, 5100001.0): volta a ser "4", "5100001"
            if all(v is None or re.fullmatch(r"\d+(\.0+)?", v) for v in conv):
                conv = [None if v is None else v.split(".")[0] for v in conv]
        for k, v in enumerate(conv):
            if v is RUIM:
                ruins.setdefault(c["nome"], []).append(bruto[k])
                conv[k] = None
        colunas.append(conv)
    for nome, vs in ruins.items():
        avisos.append(f"{nome}: {len(vs)} valor(es) não numérico(s)/inválido(s) viraram vazio (ex.: {', '.join(repr(v) for v in vs[:3])})")
    registros = [tuple(col[k] for col in colunas) for k in range(len(corpo))]
    registros = [r for r in registros if any(v is not None for v in r)]
    return Carga(t, origem, registros, avisos, mtime)


def arquivos_de(pasta: Path) -> list[Path]:
    if not pasta.exists():
        return []
    achados = []
    for p in sorted(pasta.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPORTADOS and not p.name.startswith(("~$", "._", "_", ".")) \
                and not any(part.startswith(("_", ".")) for part in p.relative_to(pasta).parts[:-1]):
            achados.append(p)
    return achados


def descobrir(pasta: Path, tabelas: dict[str, Tabela], log: list[str]) -> dict[str, list[Carga]]:
    """Lê todos os arquivos da pasta e devolve as cargas candidatas por tabela."""
    por_tabela: dict[str, list[Carga]] = {}
    for arq in arquivos_de(pasta):
        rel = arq.relative_to(pasta).as_posix()
        try:
            dados = arq.read_bytes()
            abas = abrir(arq.name, dados)
        except ImportError as e:
            log.append(f"  ✗ {rel}: falta a biblioteca para este formato ({e}). Reconstrua a imagem: docker compose build")
            continue
        except Exception as e:  # noqa: BLE001
            log.append(f"  ✗ {rel}: não consegui abrir ({type(e).__name__}: {str(e)[:120]})")
            continue
        if not abas:
            log.append(f"  – {rel}: nada para ler")
        for rotulo, linhas in abas:
            nome_visivel = f"{rel}{' · aba ' + rotulo if rotulo and len(abas) > 1 else ''}"
            if not linhas:
                log.append(f"  – {nome_visivel}: vazia")
                continue
            pelo_nome = (tabela_pelo_nome(rotulo, tabelas) if rotulo else None) or tabela_pelo_nome(arq.stem, tabelas)
            alvo, i_cab, esc = None, 0, 0.0
            if pelo_nome:
                i_cab, esc = melhor_cabecalho(linhas, pelo_nome)
                alvo = pelo_nome
                if esc < 0.34:                              # o nome diz uma coisa, as colunas outra
                    t2, i2, e2 = tabela_pelas_colunas(linhas, tabelas)
                    if t2 is not None:
                        alvo, i_cab, esc = t2, i2, e2
            else:
                alvo, i_cab, esc = tabela_pelas_colunas(linhas, tabelas)
            if alvo is None:
                log.append(f"  – {nome_visivel}: não reconheci (nome e colunas não casam com nenhuma tabela); ignorada")
                continue
            carga = converter(alvo, linhas, i_cab, nome_visivel, arq.stat().st_mtime)
            if i_cab:
                carga.avisos.insert(0, f"cabeçalho na linha {i_cab + 1}")
            por_tabela.setdefault(alvo.nome, []).append(carga)
    return por_tabela


PRIORIDADE = {".parquet": 3, ".xlsx": 2, ".xlsm": 2, ".ods": 2, ".xls": 2, ".xlsb": 2}      # o resto (texto) vale 1


def _formato(c: Carga) -> int:
    return PRIORIDADE.get(Path(c.origem.split(" · ")[0]).suffix.lower(), 1)


def escolher(cands: list[Carga]) -> tuple[Carga, list[str]]:
    """Mais recente vence; arquivos salvos com poucos minutos de diferença (CSV + Parquet do mesmo export) são gêmeos."""
    com_linhas = [c for c in cands if c.linhas] or cands
    escolhida = max(com_linhas, key=lambda c: (len(c.linhas) > 0, int(c.mtime // 300), _formato(c), c.mtime))
    gemeos = {Path(c.origem.split(" · ")[0]).with_suffix("") for c in [escolhida]}
    extras = [c.origem for c in cands if c is not escolhida and Path(c.origem.split(" · ")[0]).with_suffix("") not in gemeos]
    return escolhida, ([f"também havia {', '.join(extras)} (usei o mais recente)"] if extras else [])


# ───────────────────────── gravar o SQLite ─────────────────────────
SQL_TIPO = {"TEXT": "TEXT", "TIMESTAMP": "TEXT", "BIGINT": "INTEGER", "NUMERIC": "REAL", "BOOLEAN": "BOOLEAN"}


def gravar(destino: Path, cargas: dict[str, Carga], tabelas: dict[str, Tabela]):
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".novo")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        for nome, t in tabelas.items():
            ddl = ", ".join(f'"{c["nome"]}" {SQL_TIPO.get(c["tipo"], "TEXT")}' for c in t.colunas)
            con.execute(f'CREATE TABLE "{nome}" ({ddl})')
            carga = cargas.get(nome)
            if carga and carga.linhas:
                marcas = ",".join("?" * len(t.colunas))
                con.executemany(f'INSERT INTO "{nome}" VALUES ({marcas})', carga.linhas)
        con.commit()
    finally:
        con.close()
    os.replace(tmp, destino)         # troca atômica: quem lê vê o arquivo antigo ou o novo, nunca um pela metade


def controle_sintetico(cargas: dict[str, Carga], t: Tabela) -> Carga:
    agora = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nomes = [c["nome"] for c in t.colunas]
    linhas = []
    for nome, c in sorted(cargas.items()):
        if nome == t.nome or not c.linhas:
            continue
        reg = dict.fromkeys(nomes)
        reg.update(fonte=nome, ultimo_status="planilha", ultima_carga_sucesso_local=agora, ultima_carga_sucesso_utc=agora,
                   linhas_ultima_execucao=len(c.linhas), linhas_rejeitadas_ultima_execucao=0, ultima_transformacao_local=agora, fuso_horario="local")
        linhas.append(tuple(reg[n] for n in nomes))
    return Carga(t, "gerado a partir das planilhas carregadas", linhas, [], time.time())


def executar(somente_conferir: bool = False) -> int:
    tabelas = carregar_contrato()
    log: list[str] = []
    usuario = descobrir(PASTA, tabelas, log)
    log_fb: list[str] = []
    reserva = descobrir(FALLBACK, tabelas, log_fb) if FALLBACK != PASTA else {}

    cargas: dict[str, Carga] = {}
    notas: dict[str, list[str]] = {}
    do_usuario: set[str] = set()
    da_reserva: set[str] = set()
    for nome in tabelas:
        cands_u, cands_r = usuario.get(nome, []), reserva.get(nome, [])
        if any(c.linhas for c in cands_u):
            cargas[nome], notas[nome] = escolher(cands_u)
            do_usuario.add(nome)
        elif any(c.linhas for c in cands_r):
            cargas[nome], notas[nome] = escolher(cands_r)
            da_reserva.add(nome)
        elif cands_u or cands_r:
            cargas[nome], notas[nome] = escolher(cands_u or cands_r)
            notas[nome].insert(0, "a planilha não tem linhas de dados")
    ctl = "controle_atualizacao"
    # Misturou planilhas da equipe com a Gold exportada: o controle da Gold descreveria outra coisa, então gera um novo.
    if ctl in tabelas and ctl not in do_usuario and cargas and (do_usuario or ctl not in cargas):
        cargas[ctl] = controle_sintetico(cargas, tabelas[ctl])
        da_reserva.discard(ctl)
        notas[ctl] =["não veio planilha de controle: gerei uma a partir dos arquivos carregados"]

    print(f"== Planilhas · {dt.datetime.now():%d/%m/%Y %H:%M:%S}  (pasta: {PASTA}, reserva: {FALLBACK})")
    com_dados = 0
    for nome, t in tabelas.items():
        c = cargas.get(nome)
        if c is None:
            print(f"  ✗ {nome:<30} SEM DADOS (nenhuma planilha reconhecida; a tabela fica vazia)")
            continue
        com_dados += bool(c.linhas)
        marca = "✓" if c.linhas else "·"
        print(f"  {marca} {nome:<30} {len(c.linhas):>6} linhas  ← {c.origem}{'  [Gold exportada]' if nome in da_reserva else ''}")
        for a in c.avisos + notas.get(nome, []):
            print(f"      ! {a}")
    for l in log + [f"{x}   [reserva]" for x in log_fb]:
        print(l)

    resumo = {"gerado_em": dt.datetime.now().isoformat(timespec="seconds"), "tabelas": {
        n: {"linhas": len(c.linhas), "origem": c.origem, "avisos": c.avisos + notas.get(n, [])} for n, c in cargas.items()},
        "sem_dados": [n for n in tabelas if n not in cargas], "ignorados": log}
    if somente_conferir:
        print("(--check: nada foi gravado)")
        return 0 if com_dados else 1
    if com_dados == 0 and DB_PATH.exists():
        print(f">> nenhuma tabela com dados: mantive o banco anterior ({DB_PATH}).")
        return 1
    gravar(DB_PATH, cargas, tabelas)
    RELATORIO.write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f">> {com_dados}/{len(tabelas)} tabelas com dados -> {DB_PATH}")
    return 0 if com_dados else 1


def assinatura() -> tuple:
    itens = []
    for pasta in (PASTA, FALLBACK):
        for p in arquivos_de(pasta):
            try:
                st = p.stat()
                itens.append((str(p), st.st_size, st.st_mtime_ns))
            except OSError:
                pass
    return tuple(itens)


def vigiar(intervalo: float):
    """Recarrega quando os arquivos mudam (e já pararam de mudar: evita ler uma cópia pela metade)."""
    ultima = assinatura()
    pendente = None
    print(f">> vigiando {PASTA} e {FALLBACK} a cada {intervalo:g}s", flush=True)
    while True:
        atual = assinatura()
        if atual != ultima:
            if atual == pendente:
                try:
                    executar()
                except Exception as e:  # noqa: BLE001
                    print(f">> falha ao recarregar ({type(e).__name__}: {e}); o banco anterior continua", flush=True)
                ultima, pendente = atual, None
            else:
                pendente = atual
        else:
            pendente = None
        sys.stdout.flush()
        time.sleep(intervalo)


def modelo(caminho: Path):
    import pandas as pd
    tabelas = carregar_contrato()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    TIPO = {"TEXT": "texto", "BIGINT": "inteiro", "NUMERIC": "número (use ponto ou vírgula)", "BOOLEAN": "verdadeiro/falso", "TIMESTAMP": "data e hora"}
    with pd.ExcelWriter(caminho, engine="openpyxl") as xl:
        pd.DataFrame({"Como usar": [
            "Uma aba por tabela do dashboard. Preencha a partir da linha 2 e mantenha os cabeçalhos da linha 1.",
            "Salve em superset/planilhas/ (qualquer nome serve; vale o nome da aba). Com o Superset no ar, o dashboard atualiza sozinho em ~10 s.",
            "Vazio = sem dado (não é zero). Taxas em % (23,4 = 23,4%). Ponto ou vírgula decimal, tanto faz.",
            "Veja a aba 'colunas' para o tipo de cada coluna. Este arquivo começa com _ e por isso não é lido."]}).to_excel(xl, sheet_name="LEIA-ME", index=False)
        pd.DataFrame([(t.nome, c["nome"], TIPO.get(c["tipo"], c["tipo"]), c.get("rotulo", "")) for t in tabelas.values() for c in t.colunas],
                     columns=["tabela", "coluna", "tipo", "rótulo no dashboard"]).to_excel(xl, sheet_name="colunas", index=False)
        for t in tabelas.values():
            pd.DataFrame(columns=[c["nome"] for c in t.colunas]).to_excel(xl, sheet_name=t.nome[:31], index=False)
    print(f">> modelo gravado em {caminho}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="só confere, não grava")
    ap.add_argument("--watch", nargs="?", const=5.0, type=float, metavar="SEG", help="recarrega quando as pastas mudam")
    ap.add_argument("--modelo", metavar="ARQUIVO.xlsx", help="gera uma pasta de trabalho em branco")
    a = ap.parse_args()
    if a.modelo:
        modelo(Path(a.modelo))
        return 0
    if a.watch:
        if not DB_PATH.exists():          # no boot o init.sh já carregou uma vez antes de subir o Superset
            executar()
        vigiar(a.watch)
    return executar(a.check)


if __name__ == "__main__":
    sys.exit(main())
