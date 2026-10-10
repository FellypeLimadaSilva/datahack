from app import fontes

TABELAS = {"p2_desistencia_curso", "b1_desertos_municipio", "p4_qualidade_curso"}


def test_fonte_publica_por_tabela():
    f = fontes.fontes_de({"b1_desertos_municipio"})
    assert any(x.startswith("INEP") for x in f) and any(x.startswith("IBGE") for x in f)
    assert fontes.fontes_de({"p4_qualidade_curso"})[-1].startswith("INEP · CPC")
    assert fontes.fontes_de({"controle_atualizacao"}) == []


def test_nunca_vaza_nome_de_tabela_nas_fontes():
    for tabela in fontes.POR_TABELA:
        assert all("gold" not in f and tabela not in f for f in fontes.fontes_de({tabela}))


def _stream(texto, passo=7):
    limpa, out = fontes.Limpa(TABELAS), ""
    for i in range(0, len(texto), passo):          # chunks que cortam palavras no meio
        out += limpa.feed(texto[i:i + passo])
    return out + limpa.fim()


def test_limpa_troca_tabela_por_fonte_mesmo_cortada_no_streaming():
    out = _stream("Veja gold.p2_desistencia_curso e também p4_qualidade_curso na camada gold do warehouse.\nFim da linha.")
    assert "p2_desistencia_curso" not in out and "p4_qualidade_curso" not in out and "gold" not in out.lower()
    assert "INEP" in out


def test_limpa_preserva_texto_normal():
    texto = "# Medicina\n| Rede | Valor |\n|---|---|\n| Pública | 9,5% |\n"
    assert _stream(texto) == texto
