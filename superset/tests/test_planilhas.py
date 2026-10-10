"""Teste de ponta a ponta do carregador de planilhas (Plano B), rodando dentro da imagem do Superset.

Pega as exportações da Gold (outputs/*.parquet), grava cada tabela num formato/jeito diferente (como a equipe poderia
entregar) e confere se o SQLite montado por docker/planilhas.py tem exatamente os mesmos dados.

  powershell -File superset/tests/run_planilhas.ps1        (ou veja o comando no README)
"""
import gzip
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

OUT = Path(os.environ.get("OUTPUTS", "/outputs"))
BUNDLE = Path(os.environ.get("BUNDLE", "/bundle"))
LOADER = os.environ.get("LOADER", "/app/planilhas.py")
contrato = json.loads((BUNDLE / "contrato_planilhas.json").read_text(encoding="utf-8"))["tabelas"]
verdade = {n: pd.read_parquet(OUT / f"{n}.parquet") for n in contrato if (OUT / f"{n}.parquet").exists()}

tmp = Path(tempfile.mkdtemp())
pasta = tmp / "p"
pasta.mkdir()
(tmp / "vazia").mkdir()


def br(df):                        # como o Excel em português exporta: decimal com vírgula
    return df.astype(object).where(df.notna(), None).applymap(lambda v: str(v).replace(".", ",") if isinstance(v, float) else v)


esperado_sem_dado = {"b1_desertos_municipio"}
tem_xlwt = True
try:
    import xlwt  # noqa: F401
except ImportError:
    tem_xlwt = False
    print("(aviso) xlwt ausente: b2_financiamento_ano vai como .xlsx em vez de .xls")

# 1) xlsx com 3 linhas de título antes do cabeçalho, aba "P1 Trajetória" (nome casa pelo código p1)
d = verdade["p1_trajetoria_coorte"]
with pd.ExcelWriter(pasta / "relatorio_final.xlsx") as xl:
    pd.DataFrame([["Rota do Diploma"], ["Gerado em 10/10"], [None]]).to_excel(xl, sheet_name="P1 Trajetória", header=False, index=False)
    d.to_excel(xl, sheet_name="P1 Trajetória", startrow=3, index=False)
    pd.DataFrame({"x": [1]}).to_excel(xl, sheet_name="Notas", index=False)           # aba sem relação: ignorada
# 2) CSV ; com decimal em vírgula em cp1252, nome que não ajuda (reconhece pelas colunas)
(pasta / "base_cursos_2026.csv").write_bytes(br(verdade["p2_desistencia_curso"]).to_csv(sep=";", index=False).encode("cp1252"))
# 3) ODS com duas abas de nomes exatos
with pd.ExcelWriter(pasta / "tudo.ods", engine="odf") as xl:
    verdade["p2_desistencia_area"].to_excel(xl, sheet_name="p2_desistencia_area", index=False)
    verdade["p3_rede_modalidade_ano"].to_excel(xl, sheet_name="p3_rede_modalidade_ano", index=False)
# 4) Parquet com nome livre
verdade["p4_qualidade_curso"].to_parquet(pasta / "curso_qualidade.parquet")
# 5) JSON (lista de objetos) e JSONL
(pasta / "p4_qualidade_faixa.json").write_text(verdade["p4_qualidade_faixa"].to_json(orient="records", force_ascii=False), encoding="utf-8")
(pasta / "p4_fatores.jsonl").write_text(verdade["p4_fatores"].to_json(orient="records", lines=True, force_ascii=False), encoding="utf-8")
# 6) TSV comprimido
(pasta / "p5_licenciaturas_curso.tsv.gz").write_bytes(gzip.compress(verdade["p5_licenciaturas_curso"].to_csv(sep="\t", index=False).encode("utf-8")))
# 7) ZIP com CSV dentro
with zipfile.ZipFile(pasta / "funil.zip", "w") as z:
    z.writestr("p5_funil_licenciaturas.csv", verdade["p5_funil_licenciaturas"].to_csv(index=False))
# 8) .xls antigo (ou xlsx se não der)
if tem_xlwt:
    wb = xlwt.Workbook()                                  # o pandas 2 não escreve mais .xls: usa o xlwt direto
    ws = wb.add_sheet("dados")
    d = verdade["b2_financiamento_ano"]
    for j, c in enumerate(d.columns):
        ws.write(0, j, c)
    for i, row in enumerate(d.itertuples(index=False), start=1):
        for j, v in enumerate(row):
            if pd.notna(v):
                ws.write(i, j, v if isinstance(v, str) else float(v))
    wb.save(str(pasta / "b2_financiamento_ano.xls"))
else:
    verdade["b2_financiamento_ano"].to_excel(pasta / "b2_financiamento_ano.xlsx", index=False)
# 9) CSV com cabeçalhos em MAIÚSCULAS e sinal de % (taxa) e BOM
b = verdade["b2_financiamento_desistencia"].copy()
b.columns = [c.upper() for c in b.columns]
(pasta / "financiamento.csv").write_text(b.to_csv(index=False), encoding="utf-8-sig")
# 10) lixo que deve ser ignorado
(pasta / "~$relatorio_final.xlsx").write_bytes(b"lock")
(pasta / "leiame.txt").write_text("isto não é uma tabela\n", encoding="utf-8")
(pasta / "_rascunho.csv").write_text("a,b\n1,2\n", encoding="utf-8")
(pasta / "p2.csv").write_text("a,b\n1,2\n", encoding="utf-8")                    # 'p2' é ambíguo e as colunas não casam

env = dict(os.environ, PLANILHAS_DIR=str(pasta), FALLBACK_DIR=str(tmp / "vazia"), PLANILHAS_DB=str(tmp / "out.db"),
           PLANILHAS_CONTRATO=str(BUNDLE / "contrato_planilhas.json"))
r = subprocess.run([sys.executable, LOADER], env=env, capture_output=True, text=True)
print(r.stdout)
print(r.stderr, file=sys.stderr)
assert (tmp / "out.db").exists(), "o banco não foi criado"

con = sqlite3.connect(tmp / "out.db")
falhas = []
for nome, esp in verdade.items():
    got = pd.read_sql_query(f'SELECT * FROM "{nome}"', con)
    if nome in esperado_sem_dado or nome == "controle_atualizacao":
        continue
    if len(got) != len(esp):
        falhas.append(f"{nome}: {len(got)} linhas, esperava {len(esp)}")
        continue
    if list(got.columns) != list(esp.columns):
        falhas.append(f"{nome}: colunas diferentes")
        continue
    tipos = {c["nome"]: c["tipo"] for c in contrato[nome]["colunas"]}
    for col in esp.columns:
        a, b = got[col], esp[col]
        if tipos[col] == "NUMERIC" or tipos[col] == "BIGINT":
            ok = ((a.astype(float) - b.astype(float)).abs() < 1e-6) | (a.isna() & b.isna())
        elif tipos[col] == "BOOLEAN":
            ok = (a.astype("Int64") == b.astype(bool).astype("Int64")) | (a.isna() & b.isna())
        else:
            ok = (a.astype(str) == b.astype(str)) | (a.isna() & b.isna())
        if not ok.all():
            falhas.append(f"{nome}.{col}: {(~ok).sum()} valores diferentes (ex.: {a[~ok].head(2).tolist()} vs {b[~ok].head(2).tolist()})")
ctl = pd.read_sql_query("SELECT * FROM controle_atualizacao", con)
if ctl.empty or "p1_trajetoria_coorte" not in set(ctl["fonte"]):
    falhas.append("controle_atualizacao não foi gerado a partir das planilhas")
if con.execute('SELECT COUNT(*) FROM "b1_desertos_municipio"').fetchone()[0] != 0:
    falhas.append("b1 deveria estar vazia")
for nome in contrato:
    con.execute(f'SELECT 1 FROM "{nome}" LIMIT 1')           # todas as 13 tabelas existem

print("\n".join(["FALHAS:"] + falhas) if falhas else f"OK · {len(verdade) - 2} tabelas conferidas, 13 existem, ruídos ignorados")
sys.exit(1 if falhas else 0)# funções de conversão (planilhas de verdade têm de tudo: vírgula decimal, %, R$, sim/não, travessões)
import importlib.util
spec = importlib.util.spec_from_file_location("planilhas", LOADER)
pl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pl)
casos = [("23,40", False, 23.4), ("1.234,5", False, 1234.5), ("1,234.5", False, 1234.5), ("23,4%", False, 23.4), ("R$ 1.000,00", False, 1000.0),
         ("(5,5)", False, -5.5), ("-0,116", False, -0.116), ("28985.0", True, 28985), ("1.234", True, 1234), ("1.234.567", True, 1234567),
         ("0.116", False, 0.116), ("3.889424749", False, 3.889424749), ("--", False, None), ("SC", True, None), ("", False, None), ("NA", False, None)]
for entrada, inteiro, esperado in casos:
    obtido = pl.numero(entrada, inteiro)
    if obtido != esperado and not (isinstance(obtido, float) and esperado is not None and abs(obtido - esperado) < 1e-9):
        falhas.append(f"numero({entrada!r}, inteiro={inteiro}) = {obtido!r}, esperava {esperado!r}")
if pl.numero("abc", False) is not pl.RUIM:
    falhas.append("numero('abc') deveria ser RUIM")
for entrada, esperado in [("sim", 1), ("Verdadeiro", 1), ("TRUE", 1), ("não", 0), ("Nao", 0), ("false", 0), ("", None), ("-", None)]:
    if pl.booleano(entrada) != esperado:
        falhas.append(f"booleano({entrada!r}) = {pl.booleano(entrada)!r}, esperava {esperado!r}")
for entrada, esperado in [("Taxa Desistência Marco", "taxa_desistencia_marco"), (" Nº Cursos ", "n_cursos"), ("COORTE (ano de ingresso)", "coorte_ano_de_ingresso")]:
    if pl.norm(entrada) != esperado:
        falhas.append(f"norm({entrada!r}) = {pl.norm(entrada)!r}")


