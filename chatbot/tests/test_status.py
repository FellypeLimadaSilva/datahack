import sqlite3

from app import db


def test_status_sqlite_mostra_tabelas_e_barra_escrita(tmp_path, monkeypatch):
    path = tmp_path / "p.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE a (x int)")
    con.execute("INSERT INTO a VALUES (1), (2)")
    con.execute("CREATE TABLE b (x int)")
    con.commit()
    con.close()
    monkeypatch.setattr(db, "SQLITE_PATH", str(path))

    s = db._status_sqlite({"a", "b", "c"})
    assert s["conexao"]["ok"] and s["somente_leitura"]["ok"]
    linhas = {t["tabela"]: t for t in s["tabelas"]}
    assert linhas["a"]["linhas"] == 2 and linhas["b"]["linhas"] == 0
    assert linhas["c"]["existe"] is False


def test_status_sqlite_sem_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "SQLITE_PATH", str(tmp_path / "nao-existe.db"))
    assert db._status_sqlite({"a"})["conexao"]["ok"] is False
