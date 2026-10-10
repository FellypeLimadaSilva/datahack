"""Valida o SQL escrito pelo modelo antes de ir ao banco.

A defesa de verdade é esta camada + o papel dh_bi_reader (read-only, só schema gold),
nunca o prompt: o modelo pode errar ou ser induzido a errar.
"""
from __future__ import annotations

import os

import sqlglot
from sqlglot import exp

MAX_ROWS = 200
# Plano B (DATA_SOURCE=planilhas): as tabelas ficam soltas num SQLite, sem schema "gold".
DIALECT = "sqlite" if os.environ.get("DATA_SOURCE", "warehouse") == "planilhas" else "postgres"

# Qualquer um destes nós em qualquer ponto da árvore reprova a consulta.
_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.Set, exp.Use, exp.Copy, exp.TruncateTable, exp.Grant,
    exp.Transaction, exp.Commit, exp.Rollback, exp.Into, exp.Lock,
)
_FORBIDDEN_FUNCS = {
    "set_config", "current_setting", "dblink", "lo_import", "lo_export", "lo_get",
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "pg_terminate_backend", "pg_cancel_backend", "query_to_xml", "xpath", "copy",
    "load_extension", "readfile", "writefile", "edit", "fts3_tokenizer", "zipfile",
}


class SqlRejected(ValueError):
    """Consulta recusada; a mensagem pode ser devolvida ao modelo para ele corrigir."""


def validate(sql: str, allowed_tables: set[str], dialect: str | None = None) -> tuple[str, list[str]]:
    """Retorna (sql_seguro_com_limite, tabelas_usadas) ou levanta SqlRejected."""
    dialect = dialect or DIALECT
    if not sql or not sql.strip():
        raise SqlRejected("SQL vazio.")
    if len(sql) > 4000:
        raise SqlRejected("SQL longo demais (máx. 4000 caracteres).")
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.ParseError as e:
        raise SqlRejected(f"SQL inválido: {str(e)[:200]}") from e
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SqlRejected("Envie exatamente um comando SELECT.")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)):
        raise SqlRejected("Só consultas SELECT são permitidas.")

    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SqlRejected(f"Operação não permitida: {type(node).__name__}.")
        if isinstance(node, (exp.Anonymous, exp.Func)):
            name = (node.name or node.sql_name() or "").lower()
            if name in _FORBIDDEN_FUNCS or name.startswith(("pg_", "lo_", "sqlite_")):
                raise SqlRejected(f"Função não permitida: {name}.")
        if isinstance(node, exp.Table) and isinstance(node.this, exp.Func):
            raise SqlRejected("Funções de tabela não são permitidas.")

    ctes = {c.alias.lower() for c in tree.find_all(exp.CTE) if c.alias}
    used: set[str] = set()
    for t in tree.find_all(exp.Table):
        name = (t.name or "").lower()
        if not name:
            raise SqlRejected("Tabela sem nome.")
        if t.db and t.db.lower() != "gold":
            raise SqlRejected(f"Só o schema gold é permitido (recebi {t.db}).")
        if t.catalog:
            raise SqlRejected("Não use catálogo/banco no nome da tabela.")
        if name in ctes and not t.db:
            continue
        if name not in allowed_tables:
            raise SqlRejected(f"Tabela fora do dashboard: {name}. Permitidas: {', '.join(sorted(allowed_tables))}.")
        used.add(name)
        if dialect == "sqlite" and t.db:
            t.set("db", None)               # "gold.tabela" do dicionário vira "tabela" (o SQLite não tem schemas)
    if not used:
        raise SqlRejected("A consulta precisa ler ao menos uma tabela gold.")

    inner = tree.sql(dialect=dialect).rstrip("; ")
    return f"SELECT * FROM ({inner}) AS _q LIMIT {MAX_ROWS}", sorted(used)
