import duckdb
from . import config


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.DB_PATH), read_only=read_only)


SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id VARCHAR PRIMARY KEY, name VARCHAR, planta VARCHAR, tipo VARCHAR);
CREATE TABLE IF NOT EXISTS metrics_catalog (
    metric VARCHAR PRIMARY KEY, area VARCHAR, unidade VARCHAR, descricao VARCHAR,
    tipo_dado VARCHAR, agregacao VARCHAR,
    limite_superior DOUBLE, limite_inferior DOUBLE, referencia VARCHAR);
CREATE TABLE IF NOT EXISTS daily_metrics (
    entity_id VARCHAR, metric VARCHAR, ref_date DATE, value DOUBLE);
CREATE TABLE IF NOT EXISTS app_meta (key VARCHAR PRIMARY KEY, value VARCHAR);
CREATE TABLE IF NOT EXISTS ml_runs (
    run_id VARCHAR PRIMARY KEY, run_ts TIMESTAMP, model_version VARCHAR,
    data_max_date DATE, n_series INTEGER, n_outliers INTEGER);
CREATE TABLE IF NOT EXISTS ml_outliers (
    run_id VARCHAR, entity_id VARCHAR, metric VARCHAR, ref_date DATE,
    value DOUBLE, expected DOUBLE, score DOUBLE, is_outlier BOOLEAN);
CREATE TABLE IF NOT EXISTS ml_trends (
    run_id VARCHAR, entity_id VARCHAR, metric VARCHAR, window_days INTEGER,
    slope_per_day DOUBLE, pct_change DOUBLE, p_value DOUBLE,
    trend_direction VARCHAR, is_significant BOOLEAN);
CREATE OR REPLACE VIEW v_outliers AS
    SELECT * FROM ml_outliers
    WHERE run_id = (SELECT run_id FROM ml_runs ORDER BY run_ts DESC LIMIT 1);
CREATE OR REPLACE VIEW v_trends AS
    SELECT * FROM ml_trends
    WHERE run_id = (SELECT run_id FROM ml_runs ORDER BY run_ts DESC LIMIT 1);
"""

_DROP = """
DROP VIEW IF EXISTS v_outliers; DROP VIEW IF EXISTS v_trends;
DROP TABLE IF EXISTS ml_outliers; DROP TABLE IF EXISTS ml_trends; DROP TABLE IF EXISTS ml_runs;
DROP TABLE IF EXISTS daily_metrics; DROP TABLE IF EXISTS metrics_catalog;
DROP TABLE IF EXISTS entities; DROP TABLE IF EXISTS app_meta;
"""


def init_schema(con) -> None:
    con.execute(SCHEMA)


def reset_schema(con) -> None:
    """Apaga tudo e recria (usado pela simulação, que regrava o banco inteiro)."""
    con.execute(_DROP)
    con.execute(SCHEMA)
