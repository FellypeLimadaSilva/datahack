from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = Path(os.environ.get("DH_OUTPUTS", ROOT / "outputs"))
LAYOUT = Path(__file__).with_name("layout.json")
LOCAL_LAYOUT = Path(__file__).with_name("layout.local.json")
WIDTHS = [4, 6, 8, 12]
CODE_COLUMNS = {"co_curso": str, "co_ies": str, "co_municipio": str}
META_LABELS = {
    "pergunta": "Pergunta",
    "populacao": "População",
    "numerador": "Numerador",
    "denominador": "Denominador",
    "periodo": "Período",
    "agregacao": "Agregação",
    "grao": "Grão",
    "celulas_pequenas": "Células pequenas",
}

st.set_page_config(page_title="Rota do Diploma", layout="wide")


def _json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data
def load_table(stem: str, signature: str) -> pd.DataFrame:
    parquet = OUTPUTS / f"{stem}.parquet"
    if parquet.exists():
        return pd.read_parquet(parquet)
    return pd.read_csv(OUTPUTS / f"{stem}.csv", dtype=CODE_COLUMNS)


def load_layout() -> dict[str, Any]:
    base = _json(LAYOUT, {"blocos": []})
    local = _json(LOCAL_LAYOUT, {})
    overrides = {b["id"]: b for b in local.get("blocos", [])}
    blocks = []
    for position, block in enumerate(base["blocos"]):
        custom = overrides.get(block["id"], {})
        merged = {**block, "ordem": position}
        for key in ("visivel", "largura", "ordem"):
            if key in custom:
                merged[key] = custom[key]
        blocks.append(merged)
    base["blocos"] = sorted(blocks, key=lambda b: b["ordem"])
    return base


def save_layout(blocks: list[dict[str, Any]]) -> None:
    payload = {
        "blocos": [
            {"id": b["id"], "visivel": b["visivel"], "largura": b["largura"], "ordem": b["ordem"]}
            for b in blocks
        ]
    }
    LOCAL_LAYOUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def label(column: str, indicators: dict[str, Any], table: str) -> str:
    description = indicators.get(table, {}).get("colunas", {}).get(column, {}).get("descricao")
    return description or column.replace("_", " ")


def block_filters(block: dict[str, Any], df: pd.DataFrame) -> pd.DataFrame:
    compatible = [f for f in block.get("filtros", []) if f in df.columns]
    if not compatible:
        return df
    defaults = block.get("padrao", {})
    single = set(block.get("unico", []))
    columns = st.columns(len(compatible))
    for column, holder in zip(compatible, columns, strict=True):
        values = sorted(df[column].dropna().unique().tolist())
        if not values:
            continue
        options = values if column in single else ["Todos", *values]
        wanted = defaults.get(column)
        if wanted == "min":
            wanted = values[0]
        index = options.index(wanted) if wanted in options else 0
        choice = holder.selectbox(
            column.replace("_", " "), options, index=index, key=f"{block['id']}__{column}"
        )
        if choice != "Todos":
            df = df[df[column] == choice]
    return df


def series_column(block: dict[str, Any], df: pd.DataFrame) -> str | None:
    color = block.get("cor")
    if not color:
        return None
    if isinstance(color, list):
        df["_serie"] = df[color].astype(str).agg(" · ".join, axis=1)
        return "_serie"
    df[color] = df[color].astype(str)
    return color


def chart(block: dict[str, Any], df: pd.DataFrame, indicators: dict[str, Any]) -> None:
    table = block["tabela"]
    x, ys = block["x"], block.get("y", [])
    x_title = block.get("x_titulo", x.replace("_", " "))
    kind = block["tipo"]
    tooltip = [c for c in df.columns if not c.startswith("_")]
    if kind == "ranking":
        ranking(block, df)
        return
    if kind == "funil":
        funnel(block, df, indicators)
        return
    color = series_column(block, df)
    if len(ys) > 1:
        data = df.melt(id_vars=[c for c in df.columns if c not in ys], value_vars=ys)
        data["variable"] = data["variable"].map(lambda c: label(c, indicators, table))
        color, y, title = "variable", "value", "%"
    else:
        data, y, title = df, ys[0], label(ys[0], indicators, table)
    base = alt.Chart(data)
    encode: dict[str, Any] = {"tooltip": tooltip if len(ys) == 1 else None}
    if color:
        encode["color"] = alt.Color(f"{color}:N", title=None)
    if kind == "linha":
        mark = base.mark_line(point=True).encode(
            x=alt.X(f"{x}:O", title=x_title),
            y=alt.Y(f"{y}:Q", title=title),
            **{k: v for k, v in encode.items() if v is not None},
        )
    elif kind == "barras_h":
        mark = base.mark_bar().encode(
            y=alt.Y(f"{x}:N", sort="-x", title=None),
            x=alt.X(f"{y}:Q", title=title),
            **{k: v for k, v in encode.items() if v is not None},
        )
        if color:
            mark = mark.encode(yOffset=f"{color}:N")
    else:
        highlight = block.get("destaque")
        if highlight and highlight in data.columns and not color:
            encode["color"] = alt.condition(
                alt.datum[highlight], alt.value("#d1495b"), alt.value("#4c78a8")
            )
        mark = base.mark_bar().encode(
            x=alt.X(f"{x}:O", title=x_title),
            y=alt.Y(f"{y}:Q", title=title),
            **{k: v for k, v in encode.items() if v is not None},
        )
        if color:
            mark = mark.encode(xOffset=f"{color}:N")
    st.altair_chart(mark, width="stretch")


def ranking(block: dict[str, Any], df: pd.DataFrame) -> None:
    condition = block.get("condicao")
    if condition and condition in df.columns:
        df = df[df[condition].astype(bool)]
    metric = block["y"][0]
    columns = [c for c in block.get("colunas", df.columns) if c in df.columns]
    n = int(block.get("n", 10))
    tie = block.get("desempate")
    ordered = df.sort_values(metric, ascending=False)
    if tie and tie in df.columns:
        lowest = df.sort_values([metric, tie], ascending=[True, False]).head(n)
    else:
        lowest = ordered.tail(n).iloc[::-1]
    top, bottom = st.columns(2)
    top.caption(block.get("titulo_maiores", "Maiores"))
    top.dataframe(ordered.head(n)[columns], hide_index=True, width="stretch")
    bottom.caption(block.get("titulo_menores", "Menores"))
    bottom.dataframe(lowest[columns], hide_index=True, width="stretch")


def funnel(block: dict[str, Any], df: pd.DataFrame, indicators: dict[str, Any]) -> None:
    if df.empty:
        st.info("Sem dados para o filtro escolhido.")
        return
    row = df.iloc[0]
    steps = [("Entram", 100.0)] + [
        (label(step, indicators, block["tabela"]), row.get(step)) for step in block["etapas"]
    ]
    available = [(name, value) for name, value in steps if pd.notna(value)]
    data = pd.DataFrame(available, columns=["etapa", "de_cada_100"])
    data["ordem"] = range(len(data))
    bars = (
        alt.Chart(data)
        .mark_bar()
        .encode(
            y=alt.Y("etapa:N", sort=alt.SortField("ordem"), title=None),
            x=alt.X(
                "de_cada_100:Q",
                title="de cada 100 ingressantes",
                scale=alt.Scale(domain=[0, 100]),
            ),
            tooltip=["etapa", "de_cada_100"],
        )
    )
    text = bars.mark_text(align="left", dx=4, color="#9aa0a6").encode(
        text=alt.Text("de_cada_100:Q", format=".1f")
    )
    st.altair_chart(bars + text, width="stretch")
    notes = [
        f"{label(c, indicators, block['tabela'])}: {row.get(c):.1f}"
        for c in block.get("nota", [])
        if pd.notna(row.get(c))
    ]
    if notes:
        st.caption(" · ".join(notes))
    if len(available) < len(steps):
        st.caption("Proficiência do Enade 2025 ainda não carregada: etapa omitida.")


def metadata(block: dict[str, Any], indicators: dict[str, Any]) -> None:
    info = indicators.get(block["tabela"], {})
    meta = info.get("meta", {})
    with st.expander("Como este número é calculado"):
        if info.get("descricao"):
            st.write(info["descricao"])
        for key, title in META_LABELS.items():
            if meta.get(key):
                st.markdown(f"**{title}:** {meta[key]}")


def render(block: dict[str, Any], manifest_tables: dict[str, Any], indicators: dict[str, Any]):
    st.markdown(f"#### {block['titulo']}")
    table = block["tabela"]
    if table not in manifest_tables:
        st.info("Tabela ainda não publicada.")
        return
    signature = manifest_tables[table]
    df = load_table(table, signature).copy()
    if df.empty:
        st.info("Sem linhas publicadas (fonte opcional ainda não carregada).")
        metadata(block, indicators)
        return
    df = block_filters(block, df)
    chart(block, df, indicators)
    metadata(block, indicators)


def customize(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with st.sidebar.expander("Personalizar blocos"):
        for block in blocks:
            st.markdown(f"**{block['titulo']}**")
            left, middle, right = st.columns(3)
            block["visivel"] = left.checkbox("visível", block["visivel"], key=f"v_{block['id']}")
            block["largura"] = middle.selectbox(
                "largura",
                WIDTHS,
                index=WIDTHS.index(block["largura"]) if block["largura"] in WIDTHS else 3,
                key=f"w_{block['id']}",
            )
            block["ordem"] = right.number_input(
                "ordem", value=int(block["ordem"]), step=1, key=f"o_{block['id']}"
            )
        save, reset = st.columns(2)
        if save.button("Salvar"):
            save_layout(blocks)
            st.success("Layout salvo neste computador.")
        if reset.button("Padrão") and LOCAL_LAYOUT.exists():
            LOCAL_LAYOUT.unlink()
            st.rerun()
    return sorted(blocks, key=lambda b: b["ordem"])


def rows(blocks: list[dict[str, Any]]):
    current, used = [], 0
    for block in blocks:
        if not block["visivel"]:
            continue
        if used + block["largura"] > 12 and current:
            yield current
            current, used = [], 0
        current.append(block)
        used += block["largura"]
    if current:
        yield current


def headline(manifest_tables: dict[str, Any]) -> None:
    if "p1_trajetoria_coorte" not in manifest_tables:
        return
    p1 = load_table("p1_trajetoria_coorte", manifest_tables["p1_trajetoria_coorte"])
    p1 = p1[p1["modalidade"] == "Presencial"]
    if p1.empty:
        return
    coorte = int(p1["nu_ano_ingresso"].min())
    last = p1[p1["nu_ano_ingresso"] == coorte].sort_values("nu_ano_referencia").iloc[-1]
    st.markdown(
        f"**Coorte {coorte}, presencial, acompanhada até {int(last['nu_ano_referencia'])}**"
    )
    cols = st.columns(4)
    cols[0].metric("Ingressantes", f"{int(last['qt_ingressante']):,}".replace(",", "."))
    cols[1].metric("Concluíram (de cada 100)", f"{last['taxa_conclusao_acum']:.1f}")
    cols[2].metric("Desistiram (de cada 100)", f"{last['taxa_desistencia_acum']:.1f}")
    cols[3].metric("Seguiam matriculados", f"{last['taxa_permanencia']:.1f}")


def main() -> None:
    manifest = _json(OUTPUTS / "_manifest.json", {"tables": []})
    indicators = _json(OUTPUTS / "_indicadores.json", {})
    layout = load_layout()
    manifest_tables = {
        t["table"].split(".", 1)[1]: "|".join(f["sha256"] for f in t.get("files", []))
        for t in manifest.get("tables", [])
        if t.get("files")
    }
    st.title(layout.get("titulo", "Rota do Diploma"))
    st.caption(layout.get("subtitulo", ""))
    if not manifest_tables:
        st.warning(f"Nenhuma tabela em {OUTPUTS}. Rode: .\\scripts\\dh.ps1 pipeline")
        st.stop()
    blocks = customize(layout["blocos"])
    headline(manifest_tables)
    for row in rows(blocks):
        columns = st.columns([b["largura"] for b in row])
        for holder, block in zip(columns, row, strict=True):
            with holder:
                render(block, manifest_tables, indicators)
    sources = manifest.get("sources", {})
    files = [
        f"{name}: " + ", ".join(f["file"] for f in info.get("files", []))
        for name, info in sources.items()
        if info.get("files")
    ]
    st.divider()
    st.caption(
        f"Versão {manifest.get('version', '?')} · gerada em "
        f"{manifest.get('generated_at', '')[:16].replace('T', ' ')} UTC · "
        "Fontes públicas do INEP e do IBGE."
    )
    if files:
        st.caption("Arquivos: " + " | ".join(files))
    st.caption(
        "Grupos com menos de 10 alunos não são publicados e contagens de 1 a 9 aparecem vazias; "
        "a regra é aplicada no banco e na exportação, antes de chegar a este painel. "
        "Associações não indicam causalidade."
    )


main()
