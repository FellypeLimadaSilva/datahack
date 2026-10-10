import pytest

from app.sql_guard import SqlRejected, validate

ALLOWED = {"p2_desistencia_curso", "b1_desertos_municipio", "p1_trajetoria_coorte"}


def ok(sql):
    return validate(sql, ALLOWED)


@pytest.mark.parametrize("sql", [
    "SELECT no_curso, taxa_desistencia_marco FROM p2_desistencia_curso ORDER BY 2 DESC LIMIT 5",
    "SELECT * FROM gold.b1_desertos_municipio WHERE is_deserto",
    "WITH t AS (SELECT * FROM p2_desistencia_curso) SELECT count(*) FROM t",
    "SELECT a.nu_ano_ingresso FROM p1_trajetoria_coorte a JOIN p2_desistencia_curso b ON a.nu_ano_ingresso=b.nu_ano_ingresso;",
])
def test_aceita_select_do_dashboard(sql):
    safe, tables = ok(sql)
    assert safe.startswith("SELECT * FROM (") and safe.endswith("LIMIT 200")
    assert tables


@pytest.mark.parametrize("sql", [
    "DROP TABLE gold.p2_desistencia_curso",
    "DELETE FROM p2_desistencia_curso",
    "UPDATE p2_desistencia_curso SET no_curso='x'",
    "INSERT INTO p2_desistencia_curso VALUES (1)",
    "SELECT * FROM p2_desistencia_curso; DROP TABLE x",
    "SELECT * FROM silver.alguma_tabela",
    "SELECT * FROM bronze.censo",
    "SELECT * FROM pg_catalog.pg_user",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM tabela_inexistente",
    "SELECT pg_sleep(10)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT current_setting('is_superuser')",
    "SELECT 1",
    "SELECT * INTO nova FROM p2_desistencia_curso",
    "SET ROLE dh_admin",
    "",
    "isto nao e sql",
])
def test_recusa_perigosos(sql):
    with pytest.raises(SqlRejected):
        ok(sql)


# ───────────── Plano B: mesmo guard, dialeto SQLite (tabelas sem schema) ─────────────
def lite(sql):
    return validate(sql, ALLOWED, dialect="sqlite")


@pytest.mark.parametrize("sql", [
    "SELECT no_curso, taxa_desistencia_marco FROM p2_desistencia_curso ORDER BY 2 DESC LIMIT 5",
    "SELECT * FROM gold.b1_desertos_municipio WHERE is_deserto = 1",         # o dicionário do modo normal usa gold.
    "SELECT ROUND(100.0 * SUM(qt_desistencia_marco) / NULLIF(SUM(qt_ingressante), 0), 1) FROM p2_desistencia_curso",
])
def test_sqlite_aceita_e_tira_o_schema(sql):
    safe, tables = lite(sql)
    assert safe.startswith("SELECT * FROM (") and safe.endswith("LIMIT 200")
    assert "gold." not in safe and tables


@pytest.mark.parametrize("sql", [
    "DROP TABLE p2_desistencia_curso",
    "ATTACH DATABASE '/etc/passwd' AS x",
    "PRAGMA table_info(p2_desistencia_curso)",
    "SELECT * FROM sqlite_master",
    "SELECT load_extension('x')",
    "SELECT readfile('/etc/passwd')",
    "SELECT * FROM p2_desistencia_curso; DELETE FROM p2_desistencia_curso",
    "SELECT * FROM silver.alguma_tabela",
    "SELECT 1",
])
def test_sqlite_recusa_perigosos(sql):
    with pytest.raises(SqlRejected):
        lite(sql)
