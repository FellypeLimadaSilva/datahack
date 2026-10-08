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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="sobrescreve .env existente")
    args = ap.parse_args()

    example, target = ROOT / ".env.example", ROOT / ".env"
    if target.exists() and not args.force:
        print(f".env já existe em {target} — nada a fazer (use --force para recriar).")
        return 0

    lines = []
    for raw in example.read_text(encoding="utf-8").splitlines():
        out = raw
        if "=" in raw and not raw.lstrip().startswith("#"):
            key, value = raw.split("=", 1)
            if value.strip() == PLACEHOLDER:
                value = GENERATORS.get(key.strip(), strong_password)()
            elif key.strip() == "AIRFLOW_UID" and hasattr(os, "getuid"):
                value = str(os.getuid()) if os.getuid() != 0 else "50000"
            out = f"{key}={value}"
        lines.append(out)

    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if hasattr(os, "chmod"):
        os.chmod(target, 0o600)
    print(f".env criado em {target} com segredos aleatórios. Nunca faça commit deste arquivo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
