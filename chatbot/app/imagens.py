"""Imagens pedidas pelo usuário (mapa mental, barras, linhas, pizza).

O modelo de linguagem não gera pixels: ele descreve a imagem em JSON (ferramenta criar_imagem) e o navegador a desenha em SVG,
com botão para baixar em PNG. Este módulo valida e limita o que o modelo manda, para o front desenhar sem risco.
"""
import json
import math

TIPOS = ("mapa_mental", "barras", "linhas", "pizza")
MAX_NOS, MAX_PROFUNDIDADE, MAX_FILHOS = 70, 4, 10
MAX_CATEGORIAS, MAX_SERIES = 30, 6

FERRAMENTA = {
    "type": "function",
    "function": {
        "name": "criar_imagem",
        "description": (
            "Mostra ao usuário uma IMAGEM (que ele pode baixar em PNG) sobre o dashboard. Use quando pedirem imagem, mapa mental, "
            "gráfico, infográfico, esquema, diagrama ou desenho. Para gráficos, consulte os números antes com consultar_gold; "
            "para mapa mental do dashboard (abas, perguntas, conceitos) use o dicionário. Só assuntos do dashboard."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": list(TIPOS)},
                "titulo": {"type": "string", "description": "Título curto da imagem (até 80 caracteres)."},
                "subtitulo": {"type": "string", "description": "Opcional: recorte, ex.: «Coorte 2020 · cursos presenciais»."},
                "raiz": {
                    "type": "object",
                    "description": (
                        "Só para mapa_mental. Árvore {\"texto\": \"...\", \"filhos\": [{\"texto\": \"...\", \"filhos\": [...]}]}. "
                        f"Até {MAX_PROFUNDIDADE} níveis, {MAX_FILHOS} filhos por nó, textos curtos (até 45 caracteres)."
                    ),
                },
                "categorias": {"type": "array", "items": {"type": "string"}, "description": "Barras/linhas: rótulos do eixo (cursos, anos, redes). Pizza: as fatias."},
                "series": {
                    "type": "array",
                    "description": "Barras/linhas/pizza: [{\"nome\": \"Saíram do curso\", \"valores\": [51.1, 24.2]}]. Mesmo tamanho de categorias. Pizza usa 1 série.",
                    "items": {"type": "object"},
                },
                "unidade": {"type": "string", "description": "Ex.: «%» ou «alunos». Opcional."},
            },
            "required": ["tipo", "titulo"],
        },
    },
}


class ImagemInvalida(ValueError):
    pass


def _txt(v, n) -> str:
    return " ".join(str(v if v is not None else "").split())[:n]


def _no(raw, nivel, contador) -> dict:
    if not isinstance(raw, dict) or not _txt(raw.get("texto"), 60):
        raise ImagemInvalida("cada nó do mapa mental precisa de {\"texto\": \"...\"}.")
    contador[0] += 1
    if contador[0] > MAX_NOS:
        raise ImagemInvalida(f"mapa mental grande demais (máx. {MAX_NOS} nós): resuma.")
    filhos = raw.get("filhos") or []
    if filhos and nivel >= MAX_PROFUNDIDADE:
        raise ImagemInvalida(f"mapa mental profundo demais (máx. {MAX_PROFUNDIDADE} níveis).")
    if not isinstance(filhos, list) or len(filhos) > MAX_FILHOS:
        raise ImagemInvalida(f"no máximo {MAX_FILHOS} filhos por nó.")
    return {"texto": _txt(raw.get("texto"), 45), "filhos": [_no(f, nivel + 1, contador) for f in filhos]}


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError) as e:
        raise ImagemInvalida(f"valor não numérico: {v!r}") from e
    if not math.isfinite(x):
        raise ImagemInvalida("valor inválido (infinito ou NaN).")
    return round(x, 4)


def validar(args_json: str) -> dict:
    """Devolve a especificação limpa da imagem ou levanta ImagemInvalida (mensagem útil para o modelo corrigir)."""
    try:
        a = json.loads(args_json or "{}")
    except ValueError as e:
        raise ImagemInvalida("argumentos não são JSON válido.") from e
    if not isinstance(a, dict) or a.get("tipo") not in TIPOS:
        raise ImagemInvalida(f"tipo inválido; use um de: {', '.join(TIPOS)}.")
    spec = {"tipo": a["tipo"], "titulo": _txt(a.get("titulo"), 80) or "Rota do Diploma", "subtitulo": _txt(a.get("subtitulo"), 120),
            "unidade": _txt(a.get("unidade"), 12)}
    if a["tipo"] == "mapa_mental":
        spec["raiz"] = _no(a.get("raiz"), 1, [0])
        if not spec["raiz"]["filhos"]:
            raise ImagemInvalida("o mapa mental precisa de ramos (filhos) na raiz.")
        return spec

    cats = a.get("categorias")
    series = a.get("series")
    if not isinstance(cats, list) or not 1 <= len(cats) <= MAX_CATEGORIAS:
        raise ImagemInvalida(f"categorias: de 1 a {MAX_CATEGORIAS} rótulos.")
    if not isinstance(series, list) or not 1 <= len(series) <= MAX_SERIES:
        raise ImagemInvalida(f"series: de 1 a {MAX_SERIES} séries.")
    if a["tipo"] == "pizza":
        series = series[:1]
    spec["categorias"] = [_txt(c, 40) for c in cats]
    spec["series"] = []
    for s in series:
        if not isinstance(s, dict) or not isinstance(s.get("valores"), list) or len(s["valores"]) != len(cats):
            raise ImagemInvalida("cada série precisa de {\"nome\", \"valores\"} com um valor por categoria.")
        valores = [_num(v) for v in s["valores"]]
        if a["tipo"] == "pizza" and any(v is not None and v < 0 for v in valores):
            raise ImagemInvalida("pizza não aceita valores negativos.")
        spec["series"].append({"nome": _txt(s.get("nome"), 40) or "Valor", "valores": valores})
    return spec
