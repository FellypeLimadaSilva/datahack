# Superset na Railway: mesma imagem do superset/Dockerfile, com tudo embutido (a Railway não tem bind mount).
# Contexto de build = raiz do repositório.
FROM apache/superset:4.1.2
USER root
RUN pip install --no-cache-dir psycopg2-binary==2.9.9 openpyxl==3.1.5 xlrd==2.0.1 pyxlsb==1.0.10 odfpy==1.4.1
COPY superset/superset_config.py /app/pythonpath/superset_config_base.py
COPY deploy/superset/superset_config.py /app/pythonpath/superset_config.py
COPY superset/docker/init.sh /app/init.sh
COPY superset/docker/reimport.py /app/reimport.py
COPY superset/bundle/rota_do_diploma.zip /bundle/rota_do_diploma.zip
COPY superset/chat/tail_js_custom_extra.html /app/superset/templates/tail_js_custom_extra.html
COPY deploy/superset/entrypoint.sh /app/railway-entrypoint.sh
COPY deploy/superset/load_gold.py /app/load_gold.py
# gunicorn em dual-stack ("::"): a rede privada da Railway é IPv6, o healthcheck chega por IPv4
RUN sed -i 's#0.0.0.0:8088#[::]:8088#' /app/init.sh && chmod +x /app/railway-entrypoint.sh
# a gold que o load_gold.py carrega no Postgres a cada deploy
COPY outputs/*.parquet /app/outputs/
COPY outputs/_manifest.json /app/outputs/_manifest.json
USER superset
ENV DATA_SOURCE=warehouse OUTPUTS_DIR=/app/outputs
EXPOSE 8088
CMD ["sh", "/app/railway-entrypoint.sh"]
