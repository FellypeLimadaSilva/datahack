"""Acesso somente leitura aos dados do dashboard.

DATA_SOURCE=warehouse (padrão)  Postgres, schema gold, papel dh_bi_reader.
DATA_SOURCE=planilhas           Plano B sem banco: o SQLite que o Superset monta a partir das planilhas
                                (superset/docker/planilhas.py), aberto só para leitura em PLANILHAS_DB.
"""
from __future__ import annotations

import datetime as dt
import decimal
import os
import re
import sqlite3
import time

import psycopg

PLANILHAS = os.environ.get("DATA_SOURCE", "warehouse") == "planilhas"
DIALECT = "sqlite" if PLANILHAS else "postgres"
STATEMENT_TIMEOUT = os.environ.get("CHAT_SQL_TIMEOUT", "10s")
SQLITE_PATH = os.environ.get("PLANILHAS_DB", "/dados/planilhas.db")


def _dsn() -> str:
    return (
        f"host={os.environ.get('WAREHOUSE_HOST', 'warehouse')} port={os.environ.get('WAREHOUSE_PORT', '5432')} "
        f"dbname={os.environ.get('WAREHOUSE_DB', 'datahack')} user={os.environ['WAREHOUSE_BI_USER']} "
        f"password={os.environ['WAREHOUSE_BI_PASSWORD']} connect_timeout=5 options='-c search_path=gold'"
    )


def _plain(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def _seconds(text: str) -> float:
    m = re.search(r"[\d.]+", text)
    return float(m.group()) if m else 10.0


def _only_select(action, *_):
    # defesa em profundidade: além do SQL guard, o SQLite só aceita ler (nada de ATTACH, PRAGMA, escrita)
    ok = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE)
    return sqlite3.SQLITE_OK if action in ok else sqlite3.SQLITE_DENY


def _run_sqlite(sql: str) -> dict:
    con = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True, timeout=5)
    try:
        con.execute("PRAGMA query_only = ON")
        con.set_authorizer(_only_select)
        deadline = time.monotonic() + _seconds(STATEMENT_TIMEOUT)
        con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 50_000)
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [{c: _plain(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
    finally:
        con.close()
    return {"colunas": cols, "linhas": rows, "total_linhas": len(rows)}


def run_select(sql: str) -> dict:
    """Executa um SELECT já validado, em modo somente leitura e com timeout."""
    if PLANILHAS:
        return _run_sqlite(sql)
    with psycopg.connect(_dsn()) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            cur.execute(sql)
            cols = [d.name for d in cur.description]
            rows = [{c: _plain(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
    return {"colunas": cols, "linhas": rows, "total_linhas": len(rows)}


def _status_sqlite(tables: set[str]) -> dict:
    out: dict = {"conexao": {"ok": False}, "somente_leitura": {"ok": False}, "tabelas": [], "ultima_carga": None}
    t0 = time.perf_counter()
    try:
        con = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as e:
        out["conexao"] = {"ok": False, "detalhe": f"Sem acesso às planilhas ({SQLITE_PATH}): {e}"}
        return out
    try:
        existentes = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
        out["conexao"] = {
            "ok": True, "latencia_ms": round((time.perf_counter() - t0) * 1000),
            "detalhe": f"SQLite (Plano B, planilhas) · {SQLITE_PATH}",
        }
        for t in sorted(tables):
            row = {"tabela": t, "existe": t in existentes, "linhas": None}
            if t in existentes:
                row["linhas"] = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
            out["tabelas"].append(row)
        if "controle_atualizacao" in existentes:
            try:
                out["ultima_carga"] = con.execute("SELECT max(ultima_carga_sucesso_local) FROM controle_atualizacao").fetchone()[0]
            except sqlite3.Error:
                pass
        try:
            con.execute("CREATE TABLE _dh_probe (a int)")
            out["somente_leitura"] = {"ok": False, "detalhe": "ATENÇÃO: o arquivo aceitou escrita."}
        except sqlite3.Error as e:
            out["somente_leitura"] = {"ok": True, "detalhe": f"Escrita bloqueada (arquivo aberto só para leitura: {e})."}
    finally:
        con.close()
    return out


def status(tables: set[str]) -> dict:
    """Diagnóstico para o painel: conexão, papel somente leitura e linhas de cada tabela do dashboard."""
    if PLANILHAS:
        return _status_sqlite(tables)
    from psycopg import sql as psycopg_sql

    out: dict = {"conexao": {"ok": False}, "somente_leitura": {"ok": False}, "tabelas": [], "ultima_carga": None}
    t0 = time.perf_counter()
    try:
        with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database(), inet_server_port(), split_part(version(), ' ', 2)")
            user, dbname, port, version = cur.fetchone()
            out["conexao"] = {
                "ok": True, "latencia_ms": round((time.perf_counter() - t0) * 1000),
                "detalhe": f"{user}@{os.environ.get('WAREHOUSE_HOST', 'warehouse')}:{port}/{dbname} · PostgreSQL {version}",
            }
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'gold'")
            existentes = {r[0] for r in cur.fetchall()}
            for t in sorted(tables):
                row = {"tabela": t, "existe": t in existentes, "linhas": None}
                if t in existentes:
                    try:
                        cur.execute(psycopg_sql.SQL("SELECT count(*) FROM gold.{}").format(psycopg_sql.Identifier(t)))
                        row["linhas"] = cur.fetchone()[0]
                    except psycopg.Error:
                        row["existe"] = False
                out["tabelas"].append(row)
            if "controle_atualizacao" in existentes:
                try:
                    cur.execute("SELECT max(ultima_carga_sucesso_local)::text FROM gold.controle_atualizacao")
                    out["ultima_carga"] = cur.fetchone()[0]
                except psycopg.Error:
                    pass
    except psycopg.Error as e:
        out["conexao"] = {"ok": False, "detalhe": f"Sem conexão com o banco: {str(e).strip().splitlines()[0][:160]}"}
        return out

    # Prova de que o papel não escreve: tenta criar uma tabela numa conexão comum (sem forçar read_only) e desfaz.
    try:
        with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
            cur.execute("SHOW default_transaction_read_only")
            padrao = cur.fetchone()[0]
            try:
                cur.execute("CREATE TABLE gold._dh_probe (a int)")
                out["somente_leitura"] = {"ok": False, "detalhe": "ATENÇÃO: o papel conseguiu criar uma tabela (desfeito)."}
            except psycopg.Error as e:
                out["somente_leitura"] = {
                    "ok": True,
                    "detalhe": f"Escrita bloqueada pelo banco (default_transaction_read_only={padrao}; {type(e).__name__}).",
                }
            finally:
                conn.rollback()
    except psycopg.Error as e:
        out["somente_leitura"] = {"ok": False, "detalhe": f"Não foi possível testar: {str(e).strip().splitlines()[0][:120]}"}
    return out
