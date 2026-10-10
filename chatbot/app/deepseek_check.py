"""Teste de verdade da chave: uma chamada de 1 token ao modelo configurado (custo desprezível)."""
import datetime as dt

import openai

from . import llm


def verify(api_key: str) -> dict:
    """Retorna {"state": "green"|"red"|"amber", "message": str, "checked_at": iso}."""
    cl = openai.OpenAI(api_key=api_key, base_url=llm.BASE_URL, timeout=10, max_retries=0)
    state, msg = "green", f"Conectada e funcionando (modelo {llm.MODEL})."
    try:
        cl.chat.completions.create(
            model=llm.MODEL, max_tokens=1, messages=[{"role": "user", "content": "ok"}], extra_body=llm.NO_THINKING,
        )
    except openai.AuthenticationError:
        state, msg = "red", "Chave recusada pela DeepSeek (401). Confira se foi copiada inteira e se está ativa."
    except openai.RateLimitError:
        state, msg = "green", "Chave válida (a DeepSeek pediu para aguardar um instante: limite de requisições)."
    except (openai.APIConnectionError, openai.APITimeoutError):
        state, msg = "amber", "Sem resposta de api.deepseek.com (rede ou DNS). A chave não pôde ser verificada."
    except openai.APIStatusError as e:
        if e.status_code == 402:
            state, msg = "red", "Chave aceita, mas a conta DeepSeek está sem saldo (402)."
        elif e.status_code in (400, 404, 422):
            state, msg = "red", f"A DeepSeek recusou o modelo «{llm.MODEL}» ({e.status_code}). Escolha outro modelo nesta tela."
        else:
            state, msg = "amber", f"A DeepSeek respondeu {e.status_code}; tente testar de novo."
    except Exception as e:  # noqa: BLE001 - nunca derrubar o painel por causa do teste
        state, msg = "amber", f"Falha inesperada no teste ({type(e).__name__})."
    return {"state": state, "message": msg, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
