from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

OUTPUTS = Path(os.environ.get("DH_OUTPUTS", Path(__file__).resolve().parents[1] / "outputs"))
MAX_FILTER_VALUES = 60

st.set_page_config(page_title="DataHack", layout="wide")


@st.cache_data
def load_manifest() -> dict:
    path = OUTPUTS / "_manifest.json"
    if not path.exists():
        return {"tables": []}
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data
def load_table(stem: str) -> pd.DataFrame:
    parquet = OUTPUTS / f"{stem}.parquet"
    if parquet.exists():
        return pd.read_parquet(parquet)
    return pd.read_csv(OUTPUTS / f"{stem}.csv", dtype={"co_curso": str, "co_ies": str})


def stems(manifest: dict) -> dict[str, dict]:
    out = {}
    for table in manifest["tables"]:
        files = table.get("files") or []
        if files:
            out[Path(files[0]["file"]).stem] = table
    return out


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    for column in df.columns:
        if pd.api.types.is_numeric_dtype(df[column]) or pd.api.types.is_datetime64_any_dtype(
            df[column]
        ):
            continue
        values = df[column].dropna().unique()
        if 1 < len(values) <= MAX_FILTER_VALUES:
            chosen = st.sidebar.multiselect(column, sorted(map(str, values)))
            if chosen:
                df = df[df[column].astype(str).isin(chosen)]
    return df


def chart(df: pd.DataFrame) -> None:
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    dimensions = [c for c in df.columns if c not in numeric]
    if not numeric or not dimensions:
        return
    left, middle, right, kind_col = st.columns(4)
    x = left.selectbox("Eixo X", dimensions)
    y = middle.selectbox("Medida", numeric)
    how = right.selectbox("Agregação", ["soma", "média", "máximo", "mínimo"])
    kind = kind_col.selectbox("Gráfico", ["barras", "linha"])
    func = {"soma": "sum", "média": "mean", "máximo": "max", "mínimo": "min"}[how]
    data = df.groupby(x, dropna=False)[y].agg(func).sort_index()
    if kind == "barras":
        st.bar_chart(data)
    else:
        st.line_chart(data)


manifest = load_manifest()
available = stems(manifest)
st.title("DataHack")
if not available:
    st.warning(f"Nenhuma tabela em {OUTPUTS}. Rode a exportação: dh.ps1 export")
    st.stop()

choice = st.sidebar.selectbox("Tabela", sorted(available))
meta = available[choice]
frame = apply_filters(load_table(choice))

st.subheader(choice)
info = st.columns(3)
info[0].metric("Linhas", f"{len(frame):,}".replace(",", "."))
info[1].metric("Linhas suprimidas (< mínimo)", meta.get("suppressed_rows", 0))
info[2].metric("Gerado em", manifest.get("generated_at", "")[:16].replace("T", " "))
chart(frame)
st.dataframe(frame, width="stretch", hide_index=True)
st.download_button(
    "Baixar CSV filtrado",
    frame.to_csv(index=False).encode("utf-8"),
    file_name=f"{choice}.csv",
    mime="text/csv",
)
st.caption(
    "Dados públicos agregados. Grupos com menos alunos que o mínimo configurado são suprimidos "
    "na exportação. Relações mostradas são associações, não causalidade."
)
