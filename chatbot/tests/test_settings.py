import pytest
from fastapi.testclient import TestClient

from app import main, settings_store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "DATA_DIR", tmp_path)
    main._admin_cache.clear()
    # "sessao-admin" é o cookie de um Admin do Superset; qualquer outro é visitante
    monkeypatch.setattr(main, "_superset_is_admin", lambda cookie: "sessao-admin" in cookie)
    monkeypatch.setattr(main.deepseek_check, "verify", lambda key: {"state": "green" if key.startswith("ok-") else "red", "message": "m", "checked_at": "2026-01-01T00:00:00+00:00"})
    with TestClient(main.app) as c:
        yield c


ADMIN = {"cookie": "session=sessao-admin"}


def test_mask_nunca_revela_a_chave():
    m = settings_store.mask("sk-abcdefghijklmnop1234")
    assert m == "sk-…1234" and "abcdefghijkl" not in m


@pytest.mark.parametrize("k,ok", [("sk-abc12345", True), ("curta", False), ("com espaco 12345", False), ("sk-<script>12345", False), ("a" * 201, False)])
def test_formato_da_chave(k, ok):
    assert settings_store.valid_format(k) is ok


@pytest.mark.parametrize("headers", [{}, {"cookie": "session=visitante"}, {"x-admin-token": "qualquer-coisa"}])
def test_so_admin_do_superset_acessa(client, headers):
    assert client.get("/api/settings", headers=headers).status_code == 401
    assert client.get("/api/status", headers=headers).status_code == 401
    assert client.put("/api/settings/deepseek-key", headers=headers, json={"key": "ok-12345678"}).status_code == 401
    assert client.put("/api/settings/model", headers=headers, json={"model": "deepseek-flash"}).status_code == 401


def test_fluxo_salvar_testar_remover_com_farol(client):
    r = client.get("/api/settings", headers=ADMIN).json()["deepseek"]
    assert r["estado"] == "off" and not r["configurada"]

    r = client.put("/api/settings/deepseek-key", headers=ADMIN, json={"key": "ruim-12345678"}).json()["deepseek"]
    assert r["estado"] == "red" and r["configurada"]
    assert "ruim-12345678" not in str(r)                       # a chave não volta ao navegador

    r = client.put("/api/settings/deepseek-key", headers=ADMIN, json={"key": "ok-12345678"}).json()["deepseek"]
    assert r["estado"] == "green"
    assert client.post("/api/settings/deepseek-key/test", headers=ADMIN).json()["deepseek"]["estado"] == "green"

    r = client.delete("/api/settings/deepseek-key", headers=ADMIN).json()["deepseek"]
    assert r["estado"] == "off" and not r["configurada"]


def test_chave_fica_so_no_volume_e_nao_em_variavel_de_ambiente(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-do-ambiente-NAO-DEVE-VALER")
    assert settings_store.get_deepseek_key() is None
    client.put("/api/settings/deepseek-key", headers=ADMIN, json={"key": "ok-12345678"})
    assert settings_store.get_deepseek_key() == "ok-12345678"
    assert (tmp_path / "settings.json").exists()


def test_troca_de_modelo(client):
    r = client.put("/api/settings/model", headers=ADMIN, json={"model": "deepseek-v4-pro"}).json()["deepseek"]
    assert r["modelo"] == "deepseek-v4-pro" and settings_store.get_model() == "deepseek-v4-pro"
    assert client.put("/api/settings/model", headers=ADMIN, json={"model": "gpt-4"}).status_code == 422
    main.llm.MODEL = "deepseek-flash"


def test_formato_invalido_e_422(client):
    assert client.put("/api/settings/deepseek-key", headers=ADMIN, json={"key": "curta"}).status_code == 422


def test_chat_sem_chave_da_503(client):
    r = client.post("/chat", json={"messages": [{"role": "user", "content": "oi"}]})
    assert r.status_code == 503


def test_pagina_de_configuracoes_nao_pode_ser_embutida(client):
    r = client.get("/configuracoes")
    assert r.status_code == 200 and "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_superset_admin_decide_pelo_papel(monkeypatch):
    """_superset_is_admin pergunta ao Superset; só o papel Admin passa."""
    import httpx

    class R:
        def __init__(self, code, body): self.status_code, self._b = code, body
        def json(self): return self._b

    respostas = {"admin": R(200, {"result": {"roles": {"Admin": []}}}), "gamma": R(200, {"result": {"roles": {"Gamma": []}}}), "anon": R(401, {})}
    monkeypatch.setattr(main.httpx, "get", lambda url, headers, timeout: respostas[headers["Cookie"]])
    monkeypatch.setattr(main, "SUPERSET_URLS", ["http://x"])
    main._admin_cache.clear()
    assert main._superset_is_admin("admin") is True
    assert main._superset_is_admin("gamma") is False
    assert main._superset_is_admin("anon") is False

    def fora(*a, **k): raise httpx.ConnectError("fora do ar")
    monkeypatch.setattr(main.httpx, "get", fora)
    main._admin_cache.clear()
    assert main._superset_is_admin("admin") is False   # Superset indisponível: nega


def test_historico_com_resposta_longa_nao_da_422(client):
    """Regressão: a resposta anterior do assistente (>1000 caracteres) volta no histórico e gerava 422."""
    msgs = [
        {"role": "user", "content": "quero dados sobre medicina"},
        {"role": "assistant", "content": "x" * 5000},
        {"role": "user", "content": "qual o curso que tem mais desistencia no geral?"},
    ]
    r = client.post("/chat", json={"messages": msgs})
    assert r.status_code == 503      # sem chave: passou na validação e chegou à checagem da chave (antes era 422)
