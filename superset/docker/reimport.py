"""Conecta o Superset ao warehouse (schema gold) e importa bundle/rota_do_diploma.zip.
  python /app/reimport.py --if-missing   só importa se o dashboard ainda não existe (usado no boot)
  python /app/reimport.py --force        APAGA dashboard/gráficos/datasets deste pacote e importa de novo
A conexão com o warehouse é criada/atualizada a cada execução a partir das variáveis WAREHOUSE_* (a senha
nunca vai no pacote). O import padrão do Superset só sobrescreve o dashboard; gráficos e datasets
existentes ficam como estavam, por isso o --force.
"""
import json, os, sys
from urllib.parse import quote_plus
from zipfile import ZipFile

mode = sys.argv[1] if len(sys.argv) > 1 else "--if-missing"
ZIP = "/bundle/rota_do_diploma.zip"

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

    # 1) conexão com o warehouse (papel somente leitura dh_bi_reader)
    host, port = os.environ.get("WAREHOUSE_HOST", "warehouse"), os.environ.get("WAREHOUSE_PORT", "5432")
    name, user = os.environ.get("WAREHOUSE_DB", "datahack"), os.environ.get("WAREHOUSE_BI_USER", "dh_bi_reader")
    password = os.environ.get("WAREHOUSE_BI_PASSWORD")
    if not password:
        print(">> ERRO: defina WAREHOUSE_BI_PASSWORD (senha do dh_bi_reader no .env do repositório)")
        sys.exit(1)
    uri = f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"
    database = db.session.query(Database).filter(Database.uuid == db_conf["uuid"]).first()
    if database is None:
        database = Database(database_name=db_conf["database_name"], uuid=db_conf["uuid"], expose_in_sqllab=True, allow_dml=False)
        db.session.add(database)
    database.set_sqlalchemy_uri(uri)
    db.session.commit()
    print(f">> conexão '{database.database_name}' -> {user}@{host}:{port}/{name}")

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

    # 3) leitura anônima (a banca abre o link sem login): o papel Public precisa enxergar os datasets
    public = security_manager.find_role("Public")
    n = 0
    for t in db.session.query(SqlaTable).filter(SqlaTable.uuid.in_(by_kind["datasets"])).all():
        pv = security_manager.add_permission_view_menu("datasource_access", t.get_perm())
        security_manager.add_permission_role(public, pv)
        n += 1
    db.session.commit()
    print(f">> acesso anônimo de leitura concedido a {n} datasets")
