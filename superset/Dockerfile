FROM apache/superset:4.1.2
USER root
# psycopg2: warehouse Postgres (modo normal). As demais leem planilhas no Plano B (sem banco):
# openpyxl = xlsx/xlsm, xlrd = xls antigo, pyxlsb = xlsb, odfpy = ods. csv/tsv/json/parquet já vêm com pandas/pyarrow.
RUN pip install --no-cache-dir psycopg2-binary==2.9.9 openpyxl==3.1.5 xlrd==2.0.1 pyxlsb==1.0.10 odfpy==1.4.1
USER superset
