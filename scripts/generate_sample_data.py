from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SEED = 20261008
UFS = [
    ("Cuiabá", "MT", "Centro-Oeste"),
    ("Várzea Grande", "MT", "Centro-Oeste"),
    ("Rondonópolis", "MT", "Centro-Oeste"),
    ("Sinop", "MT", "Centro-Oeste"),
    ("Campo Grande", "MS", "Centro-Oeste"),
    ("Goiânia", "GO", "Centro-Oeste"),
    ("Porto Velho", "RO", "Norte"),
    ("Palmas", "TO", "Norte"),
]
DEPARTAMENTOS = {
    "Moda": ["Feminino", "Masculino", "Infantil", "Calçados"],
    "Casa": ["Cama", "Mesa e Banho", "Decoração"],
    "Beleza": ["Perfumaria", "Maquiagem"],
}
START, END = date(2025, 1, 1), date(2026, 9, 30)


def lojas(rng: np.random.Generator, n: int = 40) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        cidade, uf, regiao = UFS[i % len(UFS)]
        inaug = (
            date(2025, int(rng.integers(1, 10)), 1)
            if i % 5 == 0
            else date(
                int(rng.integers(2015, 2024)), int(rng.integers(1, 13)), int(rng.integers(1, 28))
            )
        )
        fechamento = date(2026, 6, 30) if i == 7 else None
        rows.append(
            {
                "Loja ID": i,
                "Nome da Loja": f"Loja {cidade} {i:02d}",
                "Cidade": cidade,
                "UF": uf,
                "Região": regiao,
                "Data Inauguração": inaug.strftime("%d/%m/%Y"),
                "Data Fechamento": fechamento.strftime("%d/%m/%Y") if fechamento else "",
                "Área (m²)": round(float(rng.uniform(300, 2500)), 1),
            }
        )
    return pd.DataFrame(rows)


def produtos(rng: np.random.Generator, n: int = 400) -> list[dict]:
    out = []
    pares = [(d, c) for d, cs in DEPARTAMENTOS.items() for c in cs]
    for i in range(1, n + 1):
        dep, cat = pares[i % len(pares)]
        out.append(
            {
                "produtoId": 1000 + i,
                "sku": f"SKU-{1000 + i:06d}",
                "nome": f"{cat} item {i}",
                "categoria": {"departamento": dep, "nome": cat},
                "precoLista": round(float(rng.uniform(19.9, 499.9)), 2),
                "ativo": bool(i % 17 != 0),
                "tags": ["promo"] if i % 9 == 0 else [],
                "atualizadoEm": f"2026-0{1 + i % 9}-15T10:00:00",
            }
        )
    return out


def vendas(rng: np.random.Generator, lojas_df: pd.DataFrame, prods: list[dict], scale: float):
    dias = pd.date_range(START, END, freq="D")
    loja_ids = lojas_df["Loja ID"].to_numpy()
    inaug = pd.to_datetime(lojas_df["Data Inauguração"], format="%d/%m/%Y").to_numpy()
    fech = pd.to_datetime(
        lojas_df["Data Fechamento"], format="%d/%m/%Y", errors="coerce"
    ).to_numpy()
    precos = {p["produtoId"]: p["precoLista"] for p in prods}
    prod_ids = np.array(list(precos))

    frames, venda_id = [], 1
    for d in dias:
        aberta = (inaug <= d.to_datetime64()) & (np.isnat(fech) | (fech >= d.to_datetime64()))
        sazonal = 1.6 if d.month in (11, 12) else (0.8 if d.month in (2, 3) else 1.0)
        fds = 1.3 if d.dayofweek >= 4 else 1.0
        for loja in loja_ids[aberta]:
            n_cupons = rng.poisson(9 * sazonal * fds * scale)
            if n_cupons == 0:
                continue
            itens = rng.integers(1, 4, n_cupons)
            ids = np.repeat(np.arange(venda_id, venda_id + n_cupons), itens)
            seq = np.concatenate([np.arange(1, k + 1) for k in itens])
            venda_id += n_cupons
            n = len(ids)
            prod = rng.choice(prod_ids, n)
            unit = np.array([precos[p] for p in prod])
            qtd = rng.integers(1, 4, n)
            desc = np.where(
                rng.random(n) < 0.25, np.round(unit * qtd * rng.uniform(0.05, 0.3, n), 2), 0.0
            )
            hora = rng.integers(9 * 3600, 22 * 3600, n_cupons)
            ts = d + pd.to_timedelta(np.repeat(hora, itens), unit="s")
            frames.append(
                pd.DataFrame(
                    {
                        "venda_id": ids,
                        "item_seq": seq,
                        "data_hora_venda": ts,
                        "loja_id": loja,
                        "produto_id": prod,
                        "quantidade": qtd,
                        "valor_unitario": unit,
                        "valor_desconto": desc,
                        "canal": rng.choice(["loja", "app", "site"], n, p=[0.7, 0.2, 0.1]),
                        "status": np.where(rng.random(n) < 0.02, "cancelada", "concluida"),
                        "cliente_cpf": np.where(
                            rng.random(n) < 0.6,
                            [f"{x:011d}" for x in rng.integers(10**9, 10**11 - 1, n)],
                            None,
                        ),
                    }
                )
            )
    df = pd.concat(frames, ignore_index=True)
    df["observacao"] = None
    df.loc[df.sample(frac=0.001, random_state=SEED).index, "observacao"] = "troca\x00pendente"
    return df


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    schema = pa.schema(
        [
            ("venda_id", pa.int64()),
            ("item_seq", pa.int32()),
            ("data_hora_venda", pa.timestamp("s")),
            ("loja_id", pa.int32()),
            ("produto_id", pa.int32()),
            ("quantidade", pa.int32()),
            ("valor_unitario", pa.float64()),
            ("valor_desconto", pa.float64()),
            ("canal", pa.string()),
            ("status", pa.string()),
            ("cliente_cpf", pa.string()),
            ("observacao", pa.string()),
        ]
    )
    pq.write_table(
        pa.Table.from_pandas(df, schema=schema, preserve_index=False), path, compression="zstd"
    )


def metas(vendas_df: pd.DataFrame) -> pd.DataFrame:
    v = vendas_df[vendas_df["status"] == "concluida"].copy()
    v["ano_mes"] = v["data_hora_venda"].dt.strftime("%Y-%m")
    v["liq"] = v["quantidade"] * v["valor_unitario"] - v["valor_desconto"]
    m = v.groupby(["loja_id", "ano_mes"], as_index=False)["liq"].sum()
    m["meta"] = (m["liq"] * 1.05).round(2)
    m["valor_meta"] = m["meta"].map(
        lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    return m[["loja_id", "ano_mes", "valor_meta"]]


def estoque(rng: np.random.Generator, lojas_df: pd.DataFrame, prods: list[dict]) -> pd.DataFrame:
    fotos = pd.date_range(START, END, freq="ME")
    prod_ids = [p["produtoId"] for p in prods[:100]]
    idx = pd.MultiIndex.from_product([fotos, lojas_df["Loja ID"], prod_ids], names=["d", "l", "p"])
    df = idx.to_frame(index=False)
    df["qtd"] = rng.integers(0, 120, len(df))
    return pd.DataFrame(
        {
            "data_foto": df["d"].dt.strftime("%Y-%m-%d"),
            "loja_id": df["l"],
            "produto_id": df["p"],
            "quantidade_estoque": df["qtd"],
        }
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/landing/sample")
    ap.add_argument("--scale", type=float, default=1.0, help="multiplicador de volume de vendas")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "vendas").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    lj = lojas(rng)
    lj.to_csv(out / "lojas.csv", index=False, encoding="utf-8")

    prods = produtos(rng)
    (out / "produtos.json").write_text(
        json.dumps({"data": {"items": prods}}, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    vd = vendas(rng, lj, prods, args.scale)
    for ano in (2025, 2026):
        write_parquet(
            vd[vd["data_hora_venda"].dt.year == ano], out / "vendas" / f"vendas_{ano}.parquet"
        )

    ajustes = (
        vd[vd["data_hora_venda"] >= pd.Timestamp(END - timedelta(days=10))]
        .sample(n=50, random_state=SEED)
        .copy()
    )
    ajustes["status"] = "cancelada"
    bad = ajustes.head(1).copy()
    bad["venda_id"] = pd.NA
    write_parquet(
        pd.concat([ajustes, bad]).astype({"venda_id": "Int64"}),
        out / "vendas" / "vendas_ajustes_2026-09.parquet",
    )

    metas(vd).to_csv(out / "metas.csv", index=False, sep=";", encoding="utf-8")
    estoque(rng, lj, prods).to_csv(out / "estoque_foto.csv", index=False)

    print(
        json.dumps(
            {"out": str(out), "lojas": len(lj), "produtos": len(prods), "itens_venda": len(vd)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
