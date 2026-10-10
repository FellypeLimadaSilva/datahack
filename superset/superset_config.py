# Superset · Rota do Diploma
import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_DB_URI"]

# Idioma
BABEL_DEFAULT_LOCALE = "pt_BR"
LANGUAGES = {"pt_BR": {"flag": "br", "name": "Português"}, "en": {"flag": "us", "name": "English"}}

FEATURE_FLAGS = {
    "DASHBOARD_CROSS_FILTERS": True,   # clicar num gráfico filtra os outros
    "DRILL_TO_DETAIL": True,           # "ver registros" a partir do gráfico
    "DRILL_BY": True,
    "DASHBOARD_NATIVE_FILTERS": True,
    "ENABLE_TEMPLATE_PROCESSING": True,
}

# Visitante anônimo só leitura (a banca abre o link sem login). Gamma + permissões do dashboard.
PUBLIC_ROLE_LIKE = "Gamma"
WTF_CSRF_ENABLED = True
TALISMAN_ENABLED = False

# Paleta categórica UNIVAG (guia de estilos v1.1: --chart-1..5) e sequencial (--seq-1..5)
EXTRA_CATEGORICAL_COLOR_SCHEMES = [{
    "id": "univag",
    "description": "UNIVAG · categórica",
    "label": "UNIVAG",
    "isDefault": True,
    "colors": ["#0066CC", "#E83E8C", "#00AEF0", "#6F42C1", "#17A2B8", "#1A2B5E", "#28A745", "#FF8C00"],
}]
EXTRA_SEQUENTIAL_COLOR_SCHEMES = [{
    "id": "univag_seq",
    "description": "UNIVAG · sequencial",
    "label": "UNIVAG sequencial",
    "isDiverging": False,
    "colors": ["#D9E8F7", "#A6C9ED", "#66A3E0", "#0066CC", "#1A2B5E"],
}]
# Cor presa ao significado (P1): concluiu = verde, saiu = vermelho, em curso = azul

# Formatação numérica pt-BR (1.234,5)
D3_FORMAT = {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["R$ ", ""]}
