# Superset · Rota do Diploma
import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_DB_URI"]

# Plano B (planilhas): a fonte é um SQLite local, que o Superset bloquearia por padrão. Só o admin cria conexões aqui.
PREVENT_UNSAFE_DB_CONNECTIONS = False

# Idioma
BABEL_DEFAULT_LOCALE = "pt_BR"
LANGUAGES = {"pt_BR": {"flag": "br", "name": "Português"}, "en": {"flag": "us", "name": "English"}}

FEATURE_FLAGS = {
    "DASHBOARD_CROSS_FILTERS": True,   # clicar num gráfico filtra os outros
    "DRILL_TO_DETAIL": True,           # "ver registros" a partir do gráfico
    "DRILL_BY": True,
    "DASHBOARD_NATIVE_FILTERS": True,
    "HORIZONTAL_FILTER_BAR": True,     # filtros em linha, no topo (gestão à vista)
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
    "colors": ["#1A2B5E", "#818AA6", "#4A5A8C", "#B4BAD0", "#2F4A8A", "#6C757D", "#0066CC", "#00AEF0"],
}]
EXTRA_SEQUENTIAL_COLOR_SCHEMES = [{
    "id": "univag_seq",
    "description": "UNIVAG · sequencial",
    "label": "UNIVAG sequencial",
    "isDiverging": False,
    "colors": ["#D9E8F7", "#A6C9ED", "#66A3E0", "#0066CC", "#1A2B5E"],
}]
# Cartões de KPI (gráfico Handlebars) precisam de style/class no HTML; só administradores editam dashboards.
HTML_SANITIZATION_SCHEMA_EXTENSIONS = {"attributes": {"*": ["style", "className"]}}

# Cor presa ao significado (P1): concluiu = verde, saiu = vermelho, em curso = azul (definido no build_bundle.js).
# Verde e vermelho ficam fora da categórica de propósito: só significam resultado.

# Fonte Roboto em toda a interface e nos gráficos (a folha da fonte é carregada pelo CSS do dashboard).
THEME_OVERRIDES = {
    "typography": {"families": {"sansSerif": "Roboto, 'Segoe UI', system-ui, -apple-system, Arial, sans-serif"}},
}

# Formatação numérica pt-BR (1.234,5)
D3_FORMAT = {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["R$ ", ""]}


# Entrada "Configurações do chat (IA)" no menu Settings (só administradores veem): chave da DeepSeek + status do banco.
# A página é servida pelo serviço do chat, no mesmo endereço do Superset (gateway: /assistente/).
def FLASK_APP_MUTATOR(app):
    from superset.extensions import appbuilder

    appbuilder.add_link(
        "Configurações do chat (IA)", href="/assistente/configuracoes", icon="fa-key", category="Manage", category_label="Manage",
    )
