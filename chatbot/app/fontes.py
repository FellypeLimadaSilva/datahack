"""Origem pública de cada tabela do dashboard.

O usuário nunca vê nome de tabela ou de coluna: ele vê de onde o dado vem (INEP, IBGE...).
"""
import re

TRAJETORIA = "INEP · Indicadores de Trajetória da Educação Superior (coortes 2015–2020, acompanhadas até 2024)"
CENSO = "INEP · Censo da Educação Superior (2021–2024)"
CPC = "INEP · CPC, Conceito Preliminar de Curso (2021–2023)"
ENADE = "INEP · Enade 2025 (cursos de licenciatura)"
IBGE = "IBGE · Censo Demográfico 2022"

# ordem de exibição das fontes
_ORDEM = [TRAJETORIA, CENSO, CPC, ENADE, IBGE]

POR_TABELA: dict[str, list[str]] = {
    "p1_trajetoria_coorte": [TRAJETORIA],
    "p2_desistencia_curso": [TRAJETORIA],
    "p2_desistencia_area": [TRAJETORIA],
    "p3_rede_modalidade_ano": [CENSO],
    "p4_qualidade_curso": [TRAJETORIA, CPC],
    "p4_qualidade_faixa": [TRAJETORIA, CPC],
    "p4_fatores": [TRAJETORIA, CPC],
    "p5_licenciaturas_curso": [TRAJETORIA, ENADE],
    "p5_funil_licenciaturas": [TRAJETORIA, ENADE],
    "b1_desertos_municipio": [CENSO, IBGE],
    "b2_financiamento_ano": [CENSO],
    "b2_financiamento_desistencia": [TRAJETORIA, CENSO],
    "controle_atualizacao": [],
}


def fontes_de(tabelas) -> list[str]:
    achadas = {f for t in tabelas for f in POR_TABELA.get(t, [])}
    return [f for f in _ORDEM if f in achadas]


def curta(tabela: str) -> str:
    """Nome curto (INEP, IBGE) para substituir um nome de tabela que escape no texto."""
    f = POR_TABELA.get(tabela) or []
    return " e ".join(dict.fromkeys(x.split(" · ")[0] for x in f)) or "dados do dashboard"


_REF = re.compile(r"\b(?:gold\.)?([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")


class Limpa:
    """Troca nomes de tabela que o modelo deixar escapar pelo nome da fonte, sem quebrar palavras no streaming."""

    def __init__(self, tabelas):
        self.tabelas = set(tabelas)
        self.resto = ""

    def _sub(self, texto: str) -> str:
        texto = _REF.sub(lambda m: curta(m.group(1)) if m.group(1) in self.tabelas else m.group(0), texto)
        return re.sub(r"\b(?:a |da |na )?camada gold( do warehouse)?\b", "os dados do dashboard", texto, flags=re.I)

    def feed(self, texto: str) -> str:
        buf = self.resto + texto
        corte = buf.rfind("\n")   # libera por linha completa: assim nenhuma expressão fica cortada ao meio
        if corte < 0:
            self.resto = buf
            return ""
        self.resto = buf[corte + 1:]
        return self._sub(buf[: corte + 1])

    def fim(self) -> str:
        out, self.resto = self._sub(self.resto), ""
        return out
