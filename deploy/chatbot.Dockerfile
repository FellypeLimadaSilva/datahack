# Chat com IA na Railway. Contexto de build = raiz do repositório (precisa do bundle do Superset e de outputs/).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY chatbot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY chatbot/app ./app
COPY chatbot/static ./static
COPY deploy/chatbot/serve.py ./serve.py
# O dicionário de dados é gerado do bundle do dashboard + indicadores (no compose local isso vem de bind mount).
COPY superset/bundle/rota_do_diploma.zip /tmp/bundle.zip
COPY outputs/_indicadores.json /knowledge/outputs/_indicadores.json
RUN python -c "import zipfile; zipfile.ZipFile('/tmp/bundle.zip').extractall('/knowledge/bundle')" && rm /tmp/bundle.zip
ENV CHAT_DATA_DIR=/data KNOWLEDGE_DIR=/knowledge
# A chave da DeepSeek é gravada em /data: monte um Volume da Railway nesse caminho (e RAILWAY_RUN_UID=0, volume nasce como root).
RUN useradd -m chat && mkdir -p /data && chown -R chat /srv /data
USER chat
EXPOSE 8099
# "::" = dual-stack: a rede privada da Railway usa IPv6, o healthcheck usa IPv4.
CMD ["python", "/srv/serve.py"]
