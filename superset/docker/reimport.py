"""Importa bundle/rota_do_diploma.zip no Superset.
  python /app/reimport.py --if-missing   só importa se o dashboard ainda não existe (usado no boot)
  python /app/reimport.py --force        APAGA dashboard/gráficos/datasets/conexão deste pacote e importa de novo
(O import padrão do Superset só sobrescreve o dashboard; gráficos e datasets existentes ficam como estavam.)
"""
import json, sys
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
    for path, text in contents.items():
        for kind in by_kind:
            if path.startswith(kind + "/") and path.endswith(".yaml"):
                by_kind[kind].append(json.loads(text)["uuid"])

    exists = db.session.query(Dashboard).filter(Dashboard.uuid.in_(by_kind["dashboards"])).count() > 0
    if mode == "--if-missing" and exists:
        print(">> dashboard já existe; nada a fazer (use --force para recriar)")
        sys.exit(0)
    if mode == "--force":
        for model, kind in ((Dashboard, "dashboards"), (Slice, "charts"), (SqlaTable, "datasets"), (Database, "databases")):
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

    # Leitura anônima (a banca abre o link sem login): o papel Public precisa enxergar os datasets do dashboard.
    public = security_manager.find_role("Public")
    n = 0
    for t in db.session.query(SqlaTable).filter(SqlaTable.uuid.in_(by_kind["datasets"])).all():
        pv = security_manager.add_permission_view_menu("datasource_access", t.get_perm())
        security_manager.add_permission_role(public, pv)
        n += 1
    db.session.commit()
    print(f">> acesso anônimo de leitura concedido a {n} datasets")
