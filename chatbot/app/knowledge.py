"""Monta o dicionário de dados do chatbot a partir do que o dashboard realmente usa.

Fontes (montadas somente leitura em /knowledge):
  - bundle do Superset (datasets, métricas, gráficos, abas, filtros);
  - outputs/_indicadores.json (população, numerador, denominador, grão por tabela gold).
A allowlist de tabelas do SQL é a lista de datasets do dashboard: o bot não enxerga mais que ele.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import fontes

from . import db

log = logging.getLogger("chatbot.knowledge")
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", "/knowledge"))


@dataclass
class Knowledge:
    tables: set[str] = field(default_factory=set)
    dictionary: str = ""
    topics: str = ""


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))  # os .yaml do bundle são JSON válido


def _bundle_dir() -> Path | None:
    base = KNOWLEDGE_DIR / "bundle"
    hits = list(base.glob("dashboard_export_*")) if base.exists() else []
    return hits[0] if hits else None


def build() -> Knowledge:
    k = Knowledge()
    ind_path = KNOWLEDGE_DIR / "outputs" / "_indicadores.json"
    indicadores = json.loads(ind_path.read_text(encoding="utf-8")) if ind_path.exists() else {}
    bundle = _bundle_dir()
    if bundle is None:
        log.warning("bundle do dashboard não encontrado em %s; dicionário ficará vazio", KNOWLEDGE_DIR)
        return k

    sqlite = db.DIALECT == "sqlite"
    parts: list[str] = [f"## Tabelas do dashboard ({'SQLite, sem schema: use só o nome da tabela' if sqlite else 'schema gold, PostgreSQL'})\n"]
    for f in sorted((bundle / "datasets").glob("*/*.yaml")):
        ds = _load(f)
        name = ds["table_name"]
        k.tables.add(name)
        parts.append(f"### {name if sqlite else 'gold.' + name}\n{ds.get('description') or ''}")
        origem = " + ".join(fontes.POR_TABELA.get(name, [])) or "painel de controle do dashboard"
        parts.append(f"- fonte pública (é ASSIM que se cita; nunca cite o nome da tabela): {origem}")
        meta = (indicadores.get(name) or {}).get("meta") or {}
        for key in ("populacao", "numerador", "denominador", "periodo", "agregacao", "grao", "celulas_pequenas"):
            if meta.get(key):
                parts.append(f"- {key}: {meta[key]}")
        cols = []
        for c in ds.get("columns", []):
            if not c.get("is_active", True) or c.get("expression"):
                continue
            label = f" — {c['verbose_name']}" if c.get("verbose_name") else ""
            cols.append(f"  - {c['column_name']} ({c.get('type')}){label}")
        parts.append("Colunas:\n" + "\n".join(cols))
        mets = [f"  - «{m.get('verbose_name') or m['metric_name']}» = {m['expression']}" for m in ds.get("metrics", [])]
        if mets:
            parts.append("Métricas do dashboard (use estas fórmulas ao reagregar):\n" + "\n".join(mets))
        parts.append("")

    parts.append("## Gráficos do dashboard (por aba)\n")
    for f in sorted((bundle / "charts").glob("*.yaml")):
        ch = _load(f)
        desc = (ch.get("description") or "").replace("Camada gold do warehouse (dbt).", "").strip()
        parts.append(f"- {ch['slice_name']}: {desc}".strip())

    dash_files = list((bundle / "dashboards").glob("*.yaml"))
    topics: list[str] = []
    if dash_files:
        dash = _load(dash_files[0])
        meta = dash.get("metadata") or {}
        pos = dash.get("position") or {}
        tabs = [v["meta"]["text"] for v in pos.values() if isinstance(v, dict) and v.get("type") == "TAB" and v.get("meta", {}).get("text")]
        filters = [f["name"] for f in meta.get("native_filter_configuration", []) if f.get("name")]
        parts.append("\n## Abas do dashboard\n" + "\n".join(f"- {t}" for t in tabs))
        parts.append("\n## Filtros do dashboard\n" + "\n".join(f"- {t}" for t in filters))
        topics = tabs
    k.topics = "; ".join(topics) if topics else "indicadores de ensino superior de Mato Grosso"
    k.dictionary = "\n".join(parts)
    log.info("dicionário: %d tabelas, %d caracteres", len(k.tables), len(k.dictionary))
    return k


if __name__ == "__main__":   # python -m app.knowledge > docs/DICIONARIO_CHATBOT.md
    print(build().dictionary)
