"""Conecta o Superset à fonte de dados e importa bundle/rota_do_diploma.zip.
  python /app/reimport.py --if-missing   só importa se o dashboard ainda não existe (usado no boot)
  python /app/reimport.py --force        APAGA dashboard/gráficos/datasets deste pacote e importa de novo
Fonte (variável DATA_SOURCE):
  warehouse (padrão)  Postgres, schema gold, papel dh_bi_reader; conexão criada/atualizada a cada execução a partir
                      das variáveis WAREHOUSE_* (a senha nunca vai no pacote).
  planilhas           Plano B sem banco: SQLite montado por planilhas.py a partir de planilhas (sem schema).
O import padrão do Superset só sobrescreve o dashboard; gráficos e datasets existentes ficam como estavam,
por isso o --force.
"""
import json, os, sys
from urllib.parse import quote_plus
from zipfile import ZipFile

mode = sys.argv[1] if len(sys.argv) > 1 else "--if-missing"
ZIP = "/bundle/rota_do_diploma.zip"
PLANILHAS = os.environ.get("DATA_SOURCE", "warehouse") == "planilhas"
SQLITE_PATH = os.environ.get("PLANILHAS_DB", "/app/superset_home/planilhas.db")
AVISO_GOLD = "Este painel lê o schema **gold** do warehouse (publicado pelo dbt após os portões de qualidade)."
AVISO_PLANILHAS = ("Este painel está no **modo planilhas (Plano B)**: lê planilhas (CSV, Excel, ODS, Parquet) carregadas num arquivo local, "
                   "sem banco de dados. Os números são os da Gold exportada ou os das planilhas colocadas na pasta superset/planilhas.")


def para_planilhas(contents: dict) -> dict:
    """Sem warehouse não existe schema 'gold': os datasets apontam para as tabelas soltas do SQLite."""
    for path, text in contents.items():
        if path.startswith("datasets/") and path.endswith(".yaml"):
            conf = json.loads(text)
            conf["schema"] = None
            contents[path] = json.dumps(conf, ensure_ascii=False)
        elif path.startswith("dashboards/") and path.endswith(".yaml"):
            conf = json.loads(text)
            for item in conf.get("position", {}).values():
                if isinstance(item, dict) and isinstance(item.get("meta", {}).get("code"), str):
                    item["meta"]["code"] = item["meta"]["code"].replace(AVISO_GOLD, AVISO_PLANILHAS)
            contents[path] = json.dumps(conf, ensure_ascii=False)
    return contents

from superset.app import create_app
app = create_app()
with app.app_context():
    from flask import g
    from superset import db, security_manager
    from superset.commands.importers.v1.utils import get_contents_from_bundle
    from superset.commands.dashboard.importers.dispatcher import ImportDashboardsCommand
    from superset.commands.exceptions import CommandInvalidError
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    g.user = security_manager.find_user(username="admin")
    with ZipFile(ZIP) as z:
        contents = get_contents_from_bundle(z)
    by_kind = {"dashboards": [], "charts": [], "datasets": [], "databases": []}
    db_conf = None
    for path, text in contents.items():
        for kind in by_kind:
            if path.startswith(kind + "/") and path.endswith(".yaml"):
                conf = json.loads(text)
                by_kind[kind].append(conf["uuid"])
                if kind == "databases":
                    db_conf = conf

    # 1) conexão: warehouse (papel somente leitura dh_bi_reader) ou, no Plano B, o SQLite das planilhas (aberto só para leitura)
    if PLANILHAS:
        uri = f"sqlite:///file:{SQLITE_PATH}?mode=ro&uri=true"
        db_name, destino = "Planilhas · gold (Plano B)", SQLITE_PATH
        contents = para_planilhas(contents)
    else:
        host, port = os.environ.get("WAREHOUSE_HOST", "warehouse"), os.environ.get("WAREHOUSE_PORT", "5432")
        name, user = os.environ.get("WAREHOUSE_DB", "datahack"), os.environ.get("WAREHOUSE_BI_USER", "dh_bi_reader")
        password = os.environ.get("WAREHOUSE_BI_PASSWORD")
        if not password:
            print(">> ERRO: defina WAREHOUSE_BI_PASSWORD (senha do dh_bi_reader no .env do repositório)")
            sys.exit(1)
        uri = f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"
        db_name, destino = db_conf["database_name"], f"{user}@{host}:{port}/{name}"
    database = db.session.query(Database).filter(Database.uuid == db_conf["uuid"]).first()
    if database is None:
        database = Database(database_name=db_name, uuid=db_conf["uuid"], expose_in_sqllab=True, allow_dml=False)
        db.session.add(database)
    database.database_name = db_name
    database.set_sqlalchemy_uri(uri)
    db.session.commit()
    print(f">> conexão '{database.database_name}' -> {destino}")

    # 2) dashboard, gráficos e datasets
    exists = db.session.query(Dashboard).filter(Dashboard.uuid.in_(by_kind["dashboards"])).count() > 0
    if mode == "--if-missing" and exists:
        print(">> dashboard já existe; nada a importar (use --force para recriar)")
        sys.exit(0)
    if mode == "--force":
        for model, kind in ((Dashboard, "dashboards"), (Slice, "charts"), (SqlaTable, "datasets")):
            for obj in db.session.query(model).filter(model.uuid.in_(by_kind[kind])).all():
                db.session.delete(obj)
            db.session.commit()
        print(">> ativos antigos removidos")
    try:
        ImportDashboardsCommand(contents, overwrite=True).run()
        print(">> IMPORT_OK")
    except CommandInvalidError as e:
        print(">> INVALIDO:", json.dumps(e.normalized_messages(), indent=1, ensure_ascii=False))
        sys.exit(1)

    # 2b) o importador do Superset traduz os ids dos gráficos na posição e nas exclusões dos filtros, mas NÃO em
    #     chart_configuration (escopo do filtro cruzado): sem isto, clicar num gráfico não filtra nada.
    dash_conf = next(json.loads(t) for p, t in contents.items() if p.startswith("dashboards/") and p.endswith(".yaml"))
    old_ids = {c["meta"]["uuid"]: c["meta"]["chartId"] for c in dash_conf["position"].values()
               if isinstance(c, dict) and c.get("type") == "CHART" and c.get("meta", {}).get("uuid")}
    dash = db.session.query(Dashboard).filter(Dashboard.uuid == dash_conf["uuid"]).one()
    new_ids = {c["meta"]["uuid"]: c["meta"]["chartId"] for c in json.loads(dash.position_json).values()
               if isinstance(c, dict) and c.get("type") == "CHART" and c.get("meta", {}).get("uuid")}
    id_map = {old: new_ids[u] for u, old in old_ids.items() if u in new_ids}
    meta = json.loads(dash.json_metadata)
    cfg = {}
    for conf in (meta.get("chart_configuration") or {}).values():
        if conf["id"] not in id_map:
            continue
        novo = id_map[conf["id"]]
        cross = conf["crossFilters"]
        cfg[str(novo)] = {"id": novo, "crossFilters": {
            "scope": {**cross["scope"], "excluded": [id_map[i] for i in cross["scope"]["excluded"] if i in id_map]},
            "chartsInScope": [id_map[i] for i in cross["chartsInScope"] if i in id_map]}}
    meta["chart_configuration"] = cfg
    dash.json_metadata = json.dumps(meta)
    db.session.commit()
    print(f">> filtro cruzado configurado em {len(cfg)} gráficos")

    # 3) leitura anônima (a banca abre o link sem login): o papel Public precisa enxergar os datasets
    public = security_manager.find_role("Public")
    n = 0
    for t in db.session.query(SqlaTable).filter(SqlaTable.uuid.in_(by_kind["datasets"])).all():
        pv = security_manager.add_permission_view_menu("datasource_access", t.get_perm())
        security_manager.add_permission_role(public, pv)
        n += 1
    db.session.commit()
    print(f">> acesso anônimo de leitura concedido a {n} datasets")
