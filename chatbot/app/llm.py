"""Loop de conversa com o DeepSeek (API compatível com OpenAI) e a ferramenta consultar_gold."""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator

from openai import OpenAI

from . import db, fontes, imagens, prompts, sql_guard
from .knowledge import Knowledge

log = logging.getLogger("chatbot.llm")

MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
MAX_TOOL_ROUNDS = 6
MAX_OUTPUT_TOKENS = 2000
MAX_TOOL_CHARS = 12000          # o que volta ao modelo de cada consulta
NO_THINKING = {"thinking": {"type": "disabled"}}

TOOLS = [{
    "type": "function",
    "function": {
        "name": "consultar_gold",
        "description": (
            f"Executa UMA consulta SELECT ({prompts.SQL_DIALECT.split(' (')[0]}) nas tabelas gold do dashboard e devolve as linhas. "
            "Só leitura, máximo 200 linhas. Use as colunas e fórmulas do dicionário."
        ),
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "Um único SELECT."}},
            "required": ["sql"],
        },
    },
}, imagens.FERRAMENTA]
MAX_IMAGENS = 3     # por resposta

# Padrões óbvios de tentativa de injeção; a barreira de verdade é o SQL guard + papel read-only.
_INJECTION = re.compile(
    r"(ignore|esque[cç]a|desconsidere)\s+(todas?\s+)?(as\s+)?(regras|instru[cç][õo]es|instructions)|"
    r"(mostre|revele|imprima|repita)\s+(o\s+)?(seu\s+)?(system\s*prompt|prompt\s+do\s+sistema|instru[cç][õo]es)|"
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions|reveal\s+(your\s+)?(system\s+)?prompt",
    re.IGNORECASE,
)


BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def client(api_key: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=BASE_URL,
        timeout=60,
        max_retries=1,
    )


def in_scope(cl: OpenAI, kn: Knowledge, text: str, user_id: str) -> bool:
    if _INJECTION.search(text):
        return False
    if os.environ.get("CHAT_SCOPE_GATE", "1") != "1":
        return True
    try:
        r = cl.chat.completions.create(
            model=MODEL, max_tokens=3, temperature=0, extra_body=NO_THINKING, user=user_id,
            messages=[
                {"role": "system", "content": prompts.SCOPE_GATE.format(topics=kn.topics)},
                {"role": "user", "content": text},
            ],
        )
        return (r.choices[0].message.content or "").strip().upper().startswith("SIM")
    except Exception:  # noqa: BLE001 - se o porteiro falhar, o system prompt ainda protege o escopo
        log.exception("porteiro de escopo falhou; seguindo sem ele")
        return True


def _run_tool(kn: Knowledge, args_json: str, sources: set[str]) -> str:
    try:
        sql = json.loads(args_json).get("sql", "")
        safe_sql, tables = sql_guard.validate(sql, kn.tables)
        result = db.run_select(safe_sql)
        sources.update(tables)
        out = json.dumps(result, ensure_ascii=False)
        if len(out) > MAX_TOOL_CHARS:
            out = out[:MAX_TOOL_CHARS] + '..."(truncado: refine a consulta com filtros ou agregação)"'
        return out
    except sql_guard.SqlRejected as e:
        return json.dumps({"erro": f"consulta recusada: {e}"}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        log.warning("falha na consulta: %s", e)
        return json.dumps({"erro": "falha ao executar a consulta; reescreva-a (verifique nomes de colunas)."}, ensure_ascii=False)


def _run_image(args_json: str, sources: set[str], ja_feitas: int) -> tuple[str, dict | None]:
    """Valida a imagem pedida pelo modelo. Devolve (resposta para o modelo, evento SSE para o navegador ou None)."""
    if ja_feitas >= MAX_IMAGENS:
        return json.dumps({"erro": f"limite de {MAX_IMAGENS} imagens por resposta."}, ensure_ascii=False), None
    try:
        spec = imagens.validar(args_json)
    except imagens.ImagemInvalida as e:
        return json.dumps({"erro": f"imagem recusada: {e}"}, ensure_ascii=False), None
    spec["fontes"] = fontes.fontes_de(sources)   # vai escrita no rodapé da imagem
    ok = {"ok": True, "mensagem": "Imagem exibida ao usuário (ele pode baixar em PNG). Comente em até 3 linhas; não repita os dados em tabela."}
    return json.dumps(ok, ensure_ascii=False), {"type": "imagem", "spec": spec}


def answer(cl: OpenAI, kn: Knowledge, history: list[dict], context: str, user_id: str) -> Iterator[dict]:
    """Gera eventos {"type": "delta"|"status"|"sources"|"done"|"error"} para o SSE."""
    system = prompts.SYSTEM.format(refusal=prompts.REFUSAL, dictionary=kn.dictionary, sql_dialect=prompts.SQL_DIALECT)
    msgs: list[dict] = [{"role": "system", "content": system}]
    if context:
        msgs.append({"role": "system", "content": context})
    msgs.extend(history)
    sources: set[str] = set()
    n_imagens = 0

    for rodada in range(MAX_TOOL_ROUNDS + 1):
        if rodada == MAX_TOOL_ROUNDS:   # última chance: sem ferramentas, responde com o que já conseguiu consultar
            msgs.append({"role": "system", "content": prompts.ULTIMA_RODADA})
        stream = cl.chat.completions.create(
            model=MODEL, messages=msgs, tools=TOOLS, tool_choice="none" if rodada == MAX_TOOL_ROUNDS else "auto", stream=True,
            max_tokens=MAX_OUTPUT_TOKENS, temperature=0.2, extra_body=NO_THINKING, user=user_id,
        )
        text, calls, sent = "", {}, 0
        limpa = fontes.Limpa(kn.tables)   # nome de tabela que escapar no texto vira o nome da fonte (INEP, IBGE...)
        for chunk in stream:
            if not chunk.choices:
                continue
            d = chunk.choices[0].delta
            if d.content:
                text += d.content
                # Comentários curtos antes de uma consulta («vou buscar...», «a consulta falhou...») não vão para o
                # usuário: só começa a mostrar quando o texto passa de 200 caracteres sem nenhuma consulta pedida.
                if not calls and len(text) > 200:
                    out = limpa.feed(text[sent:])
                    sent = len(text)
                    if out:
                        yield {"type": "delta", "text": out}
            for tc in d.tool_calls or []:
                slot = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                slot["id"] = tc.id or slot["id"]
                if tc.function:
                    slot["name"] = tc.function.name or slot["name"]
                    slot["args"] += tc.function.arguments or ""
        if not calls:
            out = limpa.feed(text[sent:]) + limpa.fim()
            if out:
                yield {"type": "delta", "text": out}
            break
        yield {"type": "status", "text": "Montando a imagem…" if any(c["name"] == "criar_imagem" for c in calls.values()) else "Consultando os dados do dashboard…"}
        msgs.append({
            "role": "assistant", "content": text or None,
            "tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["args"]}}
                for c in calls.values()
            ],
        })
        for c in calls.values():
            if c["name"] == "consultar_gold":
                content = _run_tool(kn, c["args"], sources)
            elif c["name"] == "criar_imagem":
                content, ev = _run_image(c["args"], sources, n_imagens)
                if ev:
                    n_imagens += 1
                    yield ev
            else:
                content = json.dumps({"erro": "ferramenta desconhecida"})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": content})
    else:
        yield {"type": "delta", "text": "\n\nNão consegui fechar a consulta; tente uma pergunta mais específica."}

    if sources:
        origem = fontes.fontes_de(sources)   # o navegador recebe a origem pública, nunca nomes de tabela
        if origem:
            yield {"type": "sources", "fontes": origem}
    yield {"type": "done"}
