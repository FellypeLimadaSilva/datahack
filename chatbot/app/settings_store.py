"""Guarda a chave da DeepSeek informada pelo painel (arquivo no volume /data, modo 600).

A chave nunca volta ao navegador: a API só devolve a versão mascarada. Ela vive só no volume
(DEEPSEEK_API_KEY no ambiente é ignorada de propósito; veja test_settings.py).
"""
import json
import os
import re
import tempfile
import threading
from pathlib import Path

DATA_DIR = Path(os.environ.get("CHAT_DATA_DIR", "/data"))
_lock = threading.Lock()
_KEY_RE = re.compile(r"[A-Za-z0-9_\-]{8,200}")


def _file() -> Path:
    return DATA_DIR / "settings.json"


def _read() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=".settings-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _file())
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def valid_format(key: str) -> bool:
    return bool(_KEY_RE.fullmatch(key or ""))


MODELS = ("deepseek-flash", "deepseek-v4-pro")
DEFAULT_MODEL = MODELS[0]


def get_deepseek_key() -> str | None:
    with _lock:
        return _read().get("deepseek_api_key") or None


def get_model() -> str:
    with _lock:
        saved = _read().get("model")
    return saved if saved in MODELS else DEFAULT_MODEL


def set_model(model: str) -> None:
    if model not in MODELS:
        raise ValueError(f"modelo desconhecido: {model}")
    with _lock:
        data = _read()
        data["model"] = model
        _write(data)


def set_deepseek_key(key: str) -> None:
    with _lock:
        data = _read()
        data["deepseek_api_key"] = key
        _write(data)


def clear_deepseek_key() -> None:
    with _lock:
        data = _read()
        data.pop("deepseek_api_key", None)
        _write(data)


def mask(key: str | None) -> str:
    if not key:
        return ""
    return f"{key[:3]}…{key[-4:]}" if len(key) > 10 else "…" + key[-2:]
