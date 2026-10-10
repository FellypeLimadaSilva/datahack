# Sem `from __future__ import annotations`: o decorador do slowapi esconde o namespace do módulo
# e o FastAPI deixaria de reconhecer `body: ChatIn` como corpo da requisição.
import datetime as dt
import hashlib
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from . import db, deepseek_check, knowledge, llm, prompts, settings_store

logging.basicConfig(level=os.environ.get("CHAT_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("chatbot")

RATE = os.environ.get("CHAT_RATE_LIMIT", "10/minute")
DAILY_CAP = int(os.environ.get("CHAT_DAILY_CAP", "500"))
MAX_MSG_CHARS = 1000
MAX_HISTORY = 8
PARENT_ORIGINS = os.environ.get("CHAT_PARENT_ORIGINS", "http://localhost:8088 http://127.0.0.1:8088")
STATIC = Path(__file__).resolve().parent.parent / "static"

limiter = Limiter(key_func=get_remote_address)
_cap_lock = threading.Lock()
_cap = {"day": dt.date.today(), "n": 0}
state: dict = {}
ADMIN_RATE = "30/minute"
# Onde perguntar ao Superset quem é o usuário logado (nome do serviço na rede do Docker, ou a porta no host).
SUPERSET_URLS = [u for u in os.environ.get("SUPERSET_URLS", "http://superset:8088,http://host.docker.internal:8090").split(",") if u]
_admin_cache: dict[str, tuple[float, bool]] = {}   # hash do cookie -> (expira, é admin)


@asynccontextmanager
async def lifespan(_: FastAPI):
    state["kn"] = knowledge.build()
    state["client"], state["deepseek"] = None, {"state": "off", "message": "Nenhuma chave configurada.", "checked_at": None}
    llm.MODEL = settings_store.get_model()
    key = settings_store.get_deepseek_key()
    if key:
        state["client"] = llm.client(key)
        threading.Thread(target=_check_key, args=(key,), daemon=True).start()   # farol sem travar a subida
    else:
        log.warning("Sem chave da DeepSeek: /chat responde 503 até ela ser informada em Settings > Configurações do chat (IA)")
    yield


app = FastAPI(title="Chat Rota do Diploma", lifespan=lifespan, docs_url=None, redoc_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class Msg(BaseModel):
    role: str
    content: str = Field(max_length=20000)   # respostas longas do assistente voltam como histórico; o corte é feito em chat()


class KeyIn(BaseModel):
    key: str = Field(max_length=300)


class ModelIn(BaseModel):
    model: str = Field(max_length=60)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=40)
    aba: str = Field(default="", max_length=120)
    filtros: str = Field(default="", max_length=400)


def _check_key(key: str) -> dict:
    result = deepseek_check.verify(key)
    state["deepseek"] = result
    log.info("teste da chave DeepSeek: %s", result["state"])
    return result


def _superset_is_admin(cookie: str) -> bool:
    """Pergunta ao Superset se a sessão (cookie do navegador) é de um usuário com o papel Admin."""
    k = hashlib.sha256(cookie.encode()).hexdigest()
    hit = _admin_cache.get(k)
    if hit and hit[0] > time.time():
        return hit[1]
    ok = False
    for base in SUPERSET_URLS:
        try:
            r = httpx.get(f"{base}/api/v1/me/roles/", headers={"Cookie": cookie}, timeout=3)
        except httpx.HTTPError:
            continue
        ok = r.status_code == 200 and "Admin" in (r.json().get("result", {}).get("roles") or {})
        break   # o primeiro Superset que responde decide
    if len(_admin_cache) > 200:
        _admin_cache.clear()
    _admin_cache[k] = (time.time() + 30, ok)
    return ok


def require_admin(request: Request) -> None:
    """Só quem está logado no Superset como Admin mexe nas configurações (sem token, sem arquivo .env)."""
    cookie = request.headers.get("cookie", "")
    if not cookie or not _superset_is_admin(cookie):
        raise HTTPException(401, "Entre no Superset como administrador (botão Login) e abra de novo Settings > Configurações do chat (IA).")


def _key_view() -> dict:
    key = settings_store.get_deepseek_key()
    d = state.get("deepseek") or {}
    return {
        "configurada": bool(key), "mascara": settings_store.mask(key), "modelo": llm.MODEL, "modelos": list(settings_store.MODELS),
        "estado": d.get("state", "off") if key else "off", "mensagem": d.get("message", "") if key else "Nenhuma chave configurada.",
        "verificada_em": d.get("checked_at") if key else None,
    }


def _under_daily_cap() -> bool:
    with _cap_lock:
        today = dt.date.today()
        if _cap["day"] != today:
            _cap.update(day=today, n=0)
        if _cap["n"] >= DAILY_CAP:
            return False
        _cap["n"] += 1
        return True


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.get("/healthz")
def healthz():
    kn = state.get("kn")
    return {"ok": True, "tabelas": len(kn.tables) if kn else 0, "deepseek": state.get("client") is not None}


@app.get("/api/settings")
@limiter.limit(ADMIN_RATE)
def get_settings(request: Request):
    require_admin(request)
    return {"deepseek": _key_view()}


@app.put("/api/settings/deepseek-key")
@limiter.limit(ADMIN_RATE)
def put_key(request: Request, body: KeyIn):
    require_admin(request)
    key = body.key.strip()
    if not settings_store.valid_format(key):
        raise HTTPException(422, "Formato de chave inválido (use só letras, números, - e _; 8 a 200 caracteres).")
    settings_store.set_deepseek_key(key)
    state["client"] = llm.client(key)
    _check_key(key)
    return {"deepseek": _key_view()}


@app.delete("/api/settings/deepseek-key")
@limiter.limit(ADMIN_RATE)
def delete_key(request: Request):
    require_admin(request)
    settings_store.clear_deepseek_key()
    state["client"] = None
    state["deepseek"] = {"state": "off", "message": "Nenhuma chave configurada.", "checked_at": None}
    return {"deepseek": _key_view()}


@app.post("/api/settings/deepseek-key/test")
@limiter.limit(ADMIN_RATE)
def test_key(request: Request):
    require_admin(request)
    key = settings_store.get_deepseek_key()
    if key:
        _check_key(key)
    return {"deepseek": _key_view()}


@app.put("/api/settings/model")
@limiter.limit(ADMIN_RATE)
def put_model(request: Request, body: ModelIn):
    require_admin(request)
    if body.model not in settings_store.MODELS:
        raise HTTPException(422, f"Modelo inválido. Opções: {', '.join(settings_store.MODELS)}.")
    settings_store.set_model(body.model)
    llm.MODEL = body.model
    key = settings_store.get_deepseek_key()
    if key:
        _check_key(key)   # o farol passa a refletir o novo modelo
    return {"deepseek": _key_view()}


@app.get("/api/status")
@limiter.limit(ADMIN_RATE)
def system_status(request: Request):
    require_admin(request)
    kn = state.get("kn")
    tabelas = sorted(kn.tables) if kn else []
    d = db.status(set(tabelas))
    faltando = [t["tabela"] for t in d["tabelas"] if not t["existe"]]
    vazias = [t["tabela"] for t in d["tabelas"] if t["existe"] and not t["linhas"]]
    if not d["conexao"]["ok"] or not d["somente_leitura"]["ok"]:
        geral, resumo = "red", "Banco com problema (veja os itens abaixo)."
    elif faltando:
        geral, resumo = "red", f"{len(faltando)} tabela(s) do dashboard não existem na gold: rode o pipeline."
    elif vazias:
        geral, resumo = "amber", f"Banco funcional, mas {len(vazias)} tabela(s) estão vazias (dado parcial)."
    else:
        geral, resumo = "green", "Banco funcional: conexão, somente leitura e todas as tabelas com dados."
    return {
        "geral": geral, "resumo": resumo, **d,
        "dicionario": {"ok": bool(kn and kn.tables), "tabelas": len(tabelas), "caracteres": len(kn.dictionary) if kn else 0},
        "deepseek": _key_view(),
    }


@app.get("/configuracoes")
def configuracoes_page():
    # página inteira (aberta pelo menu Settings do Superset): não pode ser embutida em outro site
    return FileResponse(STATIC / "settings.html", headers={"Content-Security-Policy": "frame-ancestors 'none'", "Cache-Control": "no-store"})


@app.get("/widget")
def widget():
    return FileResponse(
        STATIC / "chat.html",
        headers={"Content-Security-Policy": f"frame-ancestors 'self' {PARENT_ORIGINS}", "Cache-Control": "no-store"},
    )


@app.post("/chat")
@limiter.limit(RATE)
def chat(request: Request, body: ChatIn):
    client, kn = state.get("client"), state.get("kn")
    if client is None or kn is None or not kn.tables:
        return JSONResponse({"erro": "Assistente indisponível: a chave da DeepSeek ainda não foi configurada (Settings > Configurações do chat (IA)) ou o dicionário está vazio."}, status_code=503)
    if not _under_daily_cap():
        return JSONResponse({"erro": "Limite diário do assistente atingido. Volte amanhã."}, status_code=429)

    # pergunta do usuário: até 1000 caracteres; respostas antigas do assistente entram só resumidas (economiza tokens)
    limite = {"user": MAX_MSG_CHARS, "assistant": 1500}
    history = [{"role": m.role, "content": m.content[: limite[m.role]]} for m in body.messages if m.role in limite][-MAX_HISTORY:]
    if not history or history[-1]["role"] != "user":
        return JSONResponse({"erro": "A última mensagem precisa ser do usuário."}, status_code=422)
    user_id = hashlib.sha256(f"{get_remote_address(request)}".encode()).hexdigest()[:16]
    context = prompts.CONTEXT_TEMPLATE.format(aba=body.aba or "não informada", filtros=body.filtros or "nenhum") if (body.aba or body.filtros) else ""

    def events():
        try:
            if not llm.in_scope(client, kn, history[-1]["content"], user_id):
                yield _sse({"type": "delta", "text": prompts.REFUSAL})
                yield _sse({"type": "done"})
                return
            for ev in llm.answer(client, kn, history, context, user_id):
                yield _sse(ev)
        except Exception:  # noqa: BLE001
            log.exception("erro no /chat")
            yield _sse({"type": "error", "text": "Tive um problema para responder agora. Tente de novo em instantes."})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
