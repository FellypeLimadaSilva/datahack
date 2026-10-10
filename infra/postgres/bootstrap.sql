\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

SELECT format('CREATE ROLE %I LOGIN', r)
FROM unnest(ARRAY['dh_ingestor', 'dh_transformer', 'dh_bi_reader', 'dh_backup']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r)
\gexec

ALTER ROLE dh_ingestor    WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'ingest_pw' CONNECTION LIMIT 30;
ALTER ROLE dh_transformer WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'dbt_pw' CONNECTION LIMIT 30;
ALTER ROLE dh_bi_reader   WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'bi_pw' CONNECTION LIMIT 20;

ALTER ROLE dh_backup      WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'backup_pw' CONNECTION LIMIT 3;
GRANT pg_read_all_data TO dh_backup;
ALTER ROLE dh_backup      SET default_transaction_read_only = on;

ALTER ROLE dh_bi_reader   SET default_transaction_read_only = on;
ALTER ROLE dh_bi_reader   SET statement_timeout = '120s';
ALTER ROLE dh_bi_reader   SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE dh_bi_reader   SET search_path = gold;
ALTER ROLE dh_transformer SET statement_timeout = '60min';
ALTER ROLE dh_transformer SET search_path = silver, gold;
ALTER ROLE dh_transformer SET lock_timeout = '30s';
ALTER ROLE dh_ingestor    SET statement_timeout = '60min';
ALTER ROLE dh_ingestor    SET search_path = bronze, ops;

REVOKE ALL ON DATABASE :"dbname" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"dbname" TO dh_ingestor, dh_transformer, dh_bi_reader, dh_backup;
GRANT TEMPORARY ON DATABASE :"dbname" TO dh_ingestor, dh_transformer;
GRANT CREATE ON DATABASE :"dbname" TO dh_transformer;

REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA IF NOT EXISTS bronze AUTHORIZATION dh_ingestor;
CREATE SCHEMA IF NOT EXISTS ops    AUTHORIZATION dh_ingestor;
CREATE SCHEMA IF NOT EXISTS silver AUTHORIZATION dh_transformer;
CREATE SCHEMA IF NOT EXISTS gold   AUTHORIZATION dh_transformer;
CREATE SCHEMA IF NOT EXISTS gold_candidate AUTHORIZATION dh_transformer;
ALTER SCHEMA bronze OWNER TO dh_ingestor;
ALTER SCHEMA ops    OWNER TO dh_ingestor;
ALTER SCHEMA silver OWNER TO dh_transformer;
ALTER SCHEMA gold   OWNER TO dh_transformer;
ALTER SCHEMA gold_candidate OWNER TO dh_transformer;

COMMENT ON SCHEMA bronze IS 'Dado bruto fiel à origem (texto + metadados _dh_*). Acesso restrito.';
COMMENT ON SCHEMA ops    IS 'Controle e auditoria: execuções, watermarks, manifesto, rejeições.';
COMMENT ON SCHEMA silver IS 'Dado limpo, tipado, deduplicado e com PII pseudonimizada (dbt).';
COMMENT ON SCHEMA gold   IS 'Marts publicados. ÚNICA camada consumida por BI.';
COMMENT ON SCHEMA gold_candidate IS 'Versão em construção pelo dbt; só vira gold após os portões de qualidade.';

GRANT USAGE ON SCHEMA bronze, ops TO dh_transformer;
GRANT SELECT ON ALL TABLES IN SCHEMA bronze, ops TO dh_transformer;
ALTER DEFAULT PRIVILEGES FOR ROLE dh_ingestor IN SCHEMA bronze GRANT SELECT ON TABLES TO dh_transformer;
ALTER DEFAULT PRIVILEGES FOR ROLE dh_ingestor IN SCHEMA ops    GRANT SELECT ON TABLES TO dh_transformer;

GRANT USAGE ON SCHEMA gold TO dh_bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO dh_bi_reader;
REVOKE ALL ON SCHEMA bronze, ops, silver, gold_candidate FROM dh_bi_reader;

GRANT pg_read_all_stats TO dh_transformer;
