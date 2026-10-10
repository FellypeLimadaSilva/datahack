# Porta de entrada pública: dashboard (Superset) e chat saem pelo mesmo domínio.
FROM nginx:1.27-alpine
# A imagem oficial aplica envsubst em /etc/nginx/templates/*.template na subida (PORT, SUPERSET_HOST, ...).
COPY deploy/gateway/nginx.conf.template /etc/nginx/templates/default.conf.template
ENV PORT=8080 SUPERSET_HOST=superset.railway.internal SUPERSET_PORT=8088 CHAT_HOST=chatbot.railway.internal CHAT_PORT=8099 \
    DNS_RESOLVER="[fd12::10]"
