from __future__ import annotations

import argparse
import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "__GERAR__"


def fernet_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


def strong_password() -> str:
    return secrets.token_urlsafe(24)


GENERATORS = {"AIRFLOW_FERNET_KEY": fernet_key}


def _value(key: str, value: str) -> str:
    if value.strip() == PLACEHOLDER:
        return GENERATORS.get(key, strong_password)()
    if key == "AIRFLOW_UID" and hasattr(os, "getuid"):
        return str(os.getuid()) if os.getuid() != 0 else "50000"
    return value


def _pairs(text: str) -> list[tuple[str, str]]:
    out = []
    for raw in text.splitlines():
        if "=" in raw and not raw.lstrip().startswith("#"):
            key, value = raw.split("=", 1)
            out.append((key.strip(), value))
    return out


def _ensure_dirs() -> None:
    for rel in (
        "data/landing/inep/censo",
        "data/landing/inep/trajetoria",
        "data/landing/inep/qualidade",
        "outputs",
    ):
        (ROOT / rel).mkdir(parents=True, exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="sobrescreve .env existente")
    args = ap.parse_args()
    _ensure_dirs()

    example, target = ROOT / ".env.example", ROOT / ".env"
    template = example.read_text(encoding="utf-8")

    if target.exists() and not args.force:
        current = {k for k, _ in _pairs(target.read_text(encoding="utf-8"))}
        missing = [(k, v) for k, v in _pairs(template) if k not in current]
        if not missing:
            print(f".env já existe em {target} e está completo (use --force para recriar).")
            return 0
        with target.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n" + "\n".join(f"{k}={_value(k, v)}" for k, v in missing) + "\n")
        added = ", ".join(k for k, _ in missing)
        print(f".env atualizado com {len(missing)} variáveis novas: {added}")
        return 0

    lines = []
    for raw in template.splitlines():
        out = raw
        if "=" in raw and not raw.lstrip().startswith("#"):
            key, value = raw.split("=", 1)
            out = f"{key}={_value(key.strip(), value)}"
        lines.append(out)

    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if hasattr(os, "chmod"):
        os.chmod(target, 0o600)
    print(f".env criado em {target} com segredos aleatórios. Nunca faça commit deste arquivo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
