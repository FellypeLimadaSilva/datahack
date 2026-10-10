"""Sobe o chat ouvindo IPv4 e IPv6 ao mesmo tempo.

A rede privada da Railway é IPv6 e o healthcheck chega por IPv4. O uvicorn com --host "::" liga só o IPv6
(o asyncio ativa IPV6_V6ONLY), então criamos o socket dual-stack aqui e entregamos o descritor ao uvicorn.
"""
import os
import socket

import uvicorn

port = int(os.environ.get("PORT", "8099"))
try:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::", port))
except OSError:                      # contêiner sem IPv6: cai para IPv4
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
sock.listen(128)
uvicorn.run("app.main:app", fd=sock.fileno(), proxy_headers=True, forwarded_allow_ips="*")
