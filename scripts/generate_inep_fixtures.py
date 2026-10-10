from __future__ import annotations

import argparse
import csv
import io
import random
import zipfile
from pathlib import Path

from openpyxl import Workbook

UF_MT = "51"
CURSOS = [
    ("1001", "100", "DIREITO", 1, 4, 1, "Negócios, administração e direito"),
    ("1002", "100", "PEDAGOGIA", 2, 1, 1, "Educação"),
    ("1003", "200", "ENFERMAGEM", 1, 5, 1, "Saúde e bem-estar"),
    ("1004", "200", "LETRAS", 2, 4, 1, "Educação"),
    ("1005", "300", "ENGENHARIA CIVIL", 1, 1, 1, "Engenharia, produção e construção"),
    ("1006", "300", "MATEMÁTICA", 2, 2, 1, "Educação"),
]
MUNICIPIOS = [("5103403", "Cuiabá"), ("5108402", "Várzea Grande")]
TRAJETORIA_COLS = [
    "CO_IES",
    "NO_IES",
    "TP_CATEGORIA_ADMINISTRATIVA",
    "TP_ORGANIZACAO_ACADEMICA",
    "CO_CURSO",
    "NO_CURSO",
    "CO_REGIAO",
    "CO_UF",
    "CO_MUNICIPIO",
    "TP_GRAU_ACADEMICO",
    "TP_MODALIDADE_ENSINO",
    "CO_CINE_ROTULO",
    "NO_CINE_ROTULO",
    "CO_CINE_AREA_GERAL",
    "NO_CINE_AREA_GERAL",
    "NU_ANO_INGRESSO",
    "NU_ANO_REFERENCIA",
    "NU_PRAZO_INTEGRALIZACAO",
    "NU_ANO_INTEGRALIZACAO",
    "NU_PRAZO_ACOMPANHAMENTO",
    "NU_ANO_MAXIMO_ACOMPANHAMENTO",
    "QT_INGRESSANTE",
    "QT_PERMANENCIA",
    "QT_CONCLUINTE",
    "QT_DESISTENCIA",
    "QT_FALECIDO",
    "TAP",
    "TCA",
    "TDA",
    "TCAN",
    "TADA",
]
CURSOS_COLS = [
    "NU_ANO_CENSO",
    "NO_REGIAO",
    "CO_REGIAO",
    "NO_UF",
    "SG_UF",
    "CO_UF",
    "NO_MUNICIPIO",
    "CO_MUNICIPIO",
    "TP_ORGANIZACAO_ACADEMICA",
    "TP_CATEGORIA_ADMINISTRATIVA",
    "TP_REDE",
    "CO_IES",
    "NO_CURSO",
    "CO_CURSO",
    "CO_CINE_AREA_GERAL",
    "NO_CINE_AREA_GERAL",
    "TP_GRAU_ACADEMICO",
    "TP_MODALIDADE_ENSINO",
    "TP_NIVEL_ACADEMICO",
    "QT_VG_TOTAL",
    "QT_INSCRITO_TOTAL",
    "QT_ING",
    "QT_MAT",
    "QT_CONC",
    "QT_SIT_TRANCADA",
    "QT_SIT_DESVINCULADO",
    "QT_SIT_TRANSFERIDO",
    "QT_SIT_FALECIDO",
    "QT_ING_FIES",
    "QT_ING_PROUNII",
    "QT_ING_PROUNIP",
    "QT_MAT_FIES",
    "QT_MAT_PROUNII",
    "QT_MAT_PROUNIP",
]
IES_COLS = [
    "NU_ANO_CENSO",
    "SG_UF_IES",
    "CO_MUNICIPIO_IES",
    "TP_ORGANIZACAO_ACADEMICA",
    "TP_CATEGORIA_ADMINISTRATIVA",
    "CO_IES",
    "NO_IES",
    "SG_IES",
]
CPC_COLS = [
    "Ano",
    "Código da Área",
    "Área de Avaliação",
    "Código da IES",
    "Nome da IES",
    "Código do Curso",
    "Sigla da UF",
    "Nº de Concluintes Inscritos",
    "Nº de Concluintes Participantes",
    "Conceito Enade (Contínuo)",
    "Nota Padronizada - IDD",
    "Nota Padronizada - Doutores",
    "Nota Padronizada - Regime de Trabalho",
    "Nota Padronizada - Infraestrutura e Instalações Físicas",
    "Nota Padronizada - Organização Didático-Pedagógica",
    "CPC (Contínuo)",
    "CPC (Faixa)",
]
ENADE_COLS = [
    "Ano",
    "Código da Área",
    "Área de Avaliação",
    "Grau Acadêmico",
    "Código da IES",
    "Código do Curso",
    "Sigla da UF",
    "Nº de Concluintes Inscritos",
    "Nº de Concluintes Participantes",
    "Total de Concluinte igual ou acima do Padrão 1 de Proficiência",
    "Percentual de Concluintes igual ou acima do Padrão 1 de Proficiência",
    "Conceito Enade (Faixa)",
]
ENADE_PROFICIENTES = {"1002": (30, 21), "1004": (25, 10), "1006": (12, 9)}
IGC_COLS = ["Ano", "Código da IES", "Nome da IES", "Sigla da UF", "IGC (Contínuo)", "IGC (Faixa)"]


def _inep_sheet(path: Path, columns: list[str], rows: list[list], buffer: bool = False):
    wb = Workbook()
    ws = wb.active
    ws.title = "Planilha"
    ws.append(["MINISTÉRIO DA EDUCAÇÃO"])
    ws.append(["Instituto Nacional de Estudos e Pesquisas Educacionais Anísio Teixeira"])
    for _ in range(5):
        ws.append([None])
    ws.append(["Descrição das colunas na nota técnica"])
    ws.append(columns)
    for row in rows:
        ws.append(row)
    ws.append([None])
    ws.append(["Fonte: Inep. Nota: dados preliminares."])
    if buffer:
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()
    wb.save(path)
    return None


def trajetoria_rows(coorte: int, seed: int, invalid: bool = False) -> list[list]:
    rng = random.Random(seed * 1000 + coorte)
    rows = []
    for co_curso, co_ies, nome, grau, categoria, modalidade, area in CURSOS:
        ingressantes = rng.randint(40, 120)
        ativos = ingressantes
        concl_acum = desist_acum = falec_acum = 0
        for ref in range(coorte, 2025):
            ano_curso = ref - coorte + 1
            desist = min(ativos, round(ativos * rng.uniform(0.08, 0.25)))
            concl = min(ativos - desist, round(ativos * 0.3)) if ano_curso >= 4 else 0
            falec = 1 if ano_curso == 2 and ativos - desist - concl > 20 else 0
            ativos = ativos - desist - concl - falec
            concl_acum += concl
            desist_acum += desist
            falec_acum += falec
            qt_ing = "abc" if invalid and co_curso == "1001" and ref == coorte else ingressantes
            rows.append(
                [
                    co_ies,
                    f"IES {co_ies}",
                    categoria,
                    1,
                    co_curso,
                    nome,
                    5,
                    UF_MT,
                    MUNICIPIOS[0][0],
                    grau,
                    modalidade,
                    f"R{co_curso}",
                    nome,
                    "01",
                    area,
                    coorte,
                    ref,
                    5,
                    coorte + 4,
                    10,
                    coorte + 9,
                    qt_ing,
                    ativos,
                    concl,
                    desist,
                    falec,
                    round(100 * ativos / ingressantes, 6),
                    round(100 * concl_acum / ingressantes, 6),
                    round(100 * desist_acum / ingressantes, 6),
                    round(100 * concl / ingressantes, 6),
                    round(100 * desist / ingressantes, 6),
                ]
            )
    rows.append(
        [
            "999",
            "IES SP",
            4,
            1,
            "9999",
            "OUTRA UF",
            3,
            "35",
            "3550308",
            1,
            1,
            "R",
            "x",
            "01",
            "x",
            coorte,
            coorte,
            5,
            coorte + 4,
            10,
            coorte + 9,
            50,
            40,
            0,
            10,
            0,
            80,
            0,
            20,
            0,
            20,
        ]
    )
    return rows


def write_trajetoria(landing: Path, coorte: int, seed: int = 1, invalid: bool = False) -> Path:
    folder = landing / "inep" / "trajetoria"
    folder.mkdir(parents=True, exist_ok=True)
    data = _inep_sheet(Path(), TRAJETORIA_COLS, trajetoria_rows(coorte, seed, invalid), buffer=True)
    target = folder / f"indicadores_trajetoria_es_{coorte}_2024.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"indicadores_trajetoria_es_{coorte}_2024.xlsx", data)
        zf.writestr("leia_me.txt", "documentação")
    return target


def censo_rows(ano: int) -> list[list]:
    rng = random.Random(ano)
    rows = []
    for co_curso, co_ies, nome, grau, categoria, modalidade, area in CURSOS:
        rede = 1 if categoria in (1, 2, 3, 7) else 2
        for co_mun, no_mun in MUNICIPIOS:
            mat = rng.randint(50, 300)
            rows.append(
                [
                    ano,
                    "Centro-Oeste",
                    5,
                    "Mato Grosso",
                    "MT",
                    UF_MT,
                    no_mun,
                    co_mun,
                    1,
                    categoria,
                    rede,
                    co_ies,
                    nome,
                    co_curso,
                    "01",
                    area,
                    grau,
                    modalidade,
                    1,
                    rng.randint(40, 100),
                    rng.randint(100, 400),
                    rng.randint(30, 90),
                    mat,
                    rng.randint(10, 40),
                    rng.randint(5, 30),
                    rng.randint(10, 60),
                    rng.randint(0, 5),
                    0,
                    rng.randint(0, 20) if rede == 2 else 0,
                    rng.randint(0, 10) if rede == 2 else 0,
                    rng.randint(0, 10) if rede == 2 else 0,
                    rng.randint(0, 40) if rede == 2 else 0,
                    rng.randint(0, 20) if rede == 2 else 0,
                    rng.randint(0, 20) if rede == 2 else 0,
                ]
            )
    rows.append(
        [
            ano,
            "Sudeste",
            3,
            "São Paulo",
            "SP",
            "35",
            "São Paulo",
            "3550308",
            1,
            4,
            2,
            "999",
            "OUTRA",
            "9999",
            "01",
            "x",
            1,
            1,
            1,
            10,
            10,
            10,
            10,
            1,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )
    return rows


def _csv_bytes(columns: list[str], rows: list[list]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return out.getvalue().encode("cp1252")


def write_censo(landing: Path, ano: int) -> Path:
    folder = landing / "inep" / "censo"
    folder.mkdir(parents=True, exist_ok=True)
    ies = sorted({c[1]: c[4] for c in CURSOS}.items()) + [("999", 4)]
    ies_rows = [
        [ano, "MT" if co != "999" else "SP", "5103403", 1, cat, co, f"IES {co}", f"I{co}"]
        for co, cat in ies
    ]
    target = folder / f"microdados_censo_da_educacao_superior_{ano}.zip"
    base = f"Microdados do Censo da Educacao Superior {ano}"
    member_ies = "MICRODADOS_CADASTRO_IES" if ano == 2021 else "MICRODADOS_ED_SUP_IES"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"{base}/dados/MICRODADOS_CADASTRO_CURSOS_{ano}.CSV",
            _csv_bytes(CURSOS_COLS, censo_rows(ano)),
        )
        zf.writestr(f"{base}/dados/{member_ies}_{ano}.CSV", _csv_bytes(IES_COLS, ies_rows))
        zf.writestr(f"{base}/Anexos/dicionario_dados.xlsx", b"x")
    return target


def write_cpc(landing: Path, ano: int, drop: str | None = None) -> Path:
    folder = landing / "inep" / "qualidade"
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, (co_curso, co_ies, nome, *_rest) in enumerate(CURSOS):
        if (int(co_curso) + ano) % 2:
            continue
        faixa = str(2 + i % 4)
        rows.append(
            [
                ano,
                "12",
                nome,
                co_ies,
                f"IES {co_ies}",
                co_curso,
                "MT",
                40,
                35,
                f"{2.1 + i / 10:.4f}".replace(".", ","),
                2.5 + i / 10,
                3.1,
                2.9,
                2.2,
                2.7,
                2.4 + i / 5,
                faixa,
            ]
        )
    cols = list(CPC_COLS)
    if drop:
        idx = cols.index(drop)
        cols.pop(idx)
        rows = [r[:idx] + r[idx + 1 :] for r in rows]
    target = folder / f"cpc_{ano}.xlsx"
    _inep_sheet(target, cols, rows)
    return target


def write_enade(landing: Path) -> Path:
    folder = landing / "inep" / "qualidade"
    folder.mkdir(parents=True, exist_ok=True)
    rows = [
        [
            2025,
            "21",
            "LICENCIATURA",
            "Licenciatura",
            co_ies,
            co_curso,
            "MT",
            part + 2,
            part,
            prof,
            round(100 * prof / part, 1),
            "3",
        ]
        for co_curso, co_ies, *_ in CURSOS
        if co_curso in ENADE_PROFICIENTES
        for part, prof in [ENADE_PROFICIENTES[co_curso]]
    ]
    target = folder / "conceito_enade_licenciaturas.xlsx"
    _inep_sheet(target, ENADE_COLS, rows)
    return target


def write_igc(landing: Path, ano: int) -> Path:
    folder = landing / "inep" / "qualidade"
    folder.mkdir(parents=True, exist_ok=True)
    rows = [[ano, co, f"IES {co}", "MT", 2.8, "3"] for co in ("100", "200", "300")]
    target = folder / f"igc_{ano}.xlsx"
    _inep_sheet(target, IGC_COLS, rows)
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Arquivos sintéticos no layout do INEP para testes.")
    p.add_argument("--out", required=True, help="pasta landing de destino")
    args = p.parse_args(argv)
    landing = Path(args.out)
    for coorte in (2019, 2020):
        write_trajetoria(landing, coorte)
    for ano in (2021, 2023):
        write_censo(landing, ano)
    write_cpc(landing, 2021)
    write_cpc(landing, 2022)
    write_igc(landing, 2023)
    write_enade(landing)
    print(f"fixtures INEP em {landing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
