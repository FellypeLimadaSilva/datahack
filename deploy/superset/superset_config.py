# Ajustes só da Railway, por cima do superset/superset_config.py do projeto (copiado como superset_config_base).
import os

from superset_config_base import *  # noqa: F401,F403

# Atrás do edge da Railway e do nginx do gateway: respeita X-Forwarded-Proto/For (URLs https, cookie Secure).
ENABLE_PROXY_FIX = True
PROXY_FIX_CONFIG = {"x_for": 1, "x_proto": 1, "x_host": 0, "x_port": 0, "x_prefix": 0}
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
