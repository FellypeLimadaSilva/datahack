import json

import pytest

from app import imagens, llm


def v(**kw):
    return imagens.validar(json.dumps(kw))


def test_mapa_mental_valido_e_textos_limpos():
    s = v(tipo="mapa_mental", titulo="Medicina", raiz={"texto": "Medicina", "filhos": [{"texto": "  Rede  pública ", "filhos": [{"texto": "9,5% saem"}]}]})
    assert s["raiz"]["filhos"][0]["texto"] == "Rede pública"
    assert s["raiz"]["filhos"][0]["filhos"][0]["filhos"] == []


@pytest.mark.parametrize("raiz", [
    {"texto": "so a raiz"},                                                       # sem ramos
    {"texto": "x", "filhos": [{"sem_texto": 1}]},
    {"texto": "x", "filhos": [{"texto": str(i)} for i in range(11)]},             # filhos demais
    {"texto": "a", "filhos": [{"texto": "b", "filhos": [{"texto": "c", "filhos": [{"texto": "d", "filhos": [{"texto": "e"}]}]}]}]},  # fundo demais
])
def test_mapa_mental_invalido(raiz):
    with pytest.raises(imagens.ImagemInvalida):
        v(tipo="mapa_mental", titulo="t", raiz=raiz)


def test_barras_ok_e_aceita_valor_vazio():
    s = v(tipo="barras", titulo="t", categorias=["A", "B"], series=[{"nome": "S", "valores": [1, None]}], unidade="%")
    assert s["series"][0]["valores"] == [1.0, None] and s["unidade"] == "%"


@pytest.mark.parametrize("kw", [
    {"tipo": "foto", "titulo": "t"},                                                             # tipo desconhecido
    {"tipo": "barras", "titulo": "t", "categorias": ["A", "B"], "series": [{"nome": "S", "valores": [1]}]},   # tamanhos diferentes
    {"tipo": "barras", "titulo": "t", "categorias": ["A"], "series": [{"nome": "S", "valores": ["abc"]}]},    # não numérico
    {"tipo": "barras", "titulo": "t", "categorias": [], "series": []},
    {"tipo": "pizza", "titulo": "t", "categorias": ["A"], "series": [{"nome": "S", "valores": [-1]}]},
    {"tipo": "linhas", "titulo": "t", "categorias": ["A"], "series": [{"nome": "S", "valores": [float("inf")]}]},
])
def test_graficos_invalidos(kw):
    with pytest.raises(imagens.ImagemInvalida):
        imagens.validar(json.dumps(kw))


def test_json_quebrado():
    with pytest.raises(imagens.ImagemInvalida):
        imagens.validar("{nao é json")


def test_pizza_usa_so_a_primeira_serie():
    s = v(tipo="pizza", titulo="t", categorias=["A", "B"], series=[{"nome": "1", "valores": [1, 2]}, {"nome": "2", "valores": [3, 4]}])
    assert len(s["series"]) == 1


def test_evento_de_imagem_leva_so_a_fonte_publica():
    args = json.dumps({"tipo": "barras", "titulo": "t", "categorias": ["A"], "series": [{"nome": "S", "valores": [1]}]})
    resposta, ev = llm._run_image(args, {"p4_qualidade_curso"}, 0)
    assert json.loads(resposta)["ok"] and ev["type"] == "imagem"
    assert all("gold" not in f and "p4_" not in f for f in ev["spec"]["fontes"])
    assert any(f.startswith("INEP") for f in ev["spec"]["fontes"])


def test_limite_de_imagens_por_resposta():
    args = json.dumps({"tipo": "barras", "titulo": "t", "categorias": ["A"], "series": [{"nome": "S", "valores": [1]}]})
    resposta, ev = llm._run_image(args, set(), llm.MAX_IMAGENS)
    assert ev is None and "limite" in json.loads(resposta)["erro"]


def test_ferramenta_registrada():
    assert {t["function"]["name"] for t in llm.TOOLS} == {"consultar_gold", "criar_imagem"}
