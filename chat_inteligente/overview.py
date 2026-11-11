"""Status do banco (barra lateral) e navegação nas tabelas (aba Dados)."""
import pandas as pd
from .db import connect


def _df(sql: str, params=None) -> pd.DataFrame:
    con = connect(read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()


def status() -> dict:
    try:
        cols = set(_df("SELECT * FROM entities LIMIT 0").columns)
        if "planta" not in cols or _df("SELECT COUNT(*) AS n FROM information_schema.tables "
                                       "WHERE table_name='metrics_catalog'")["n"].iloc[0] == 0:
            return {"ok": False, "reason": "Banco no formato antigo: rode synth e run_daily para regerar."}
        b = _df("""SELECT COUNT(DISTINCT entity_id) AS n_entities,
                   COUNT(DISTINCT entity_id || '|' || metric) AS n_series, COUNT(*) AS n_rows,
                   MIN(ref_date) AS date_min, MAX(ref_date) AS date_max
                   FROM daily_metrics""").iloc[0]
        run = _df("SELECT * FROM ml_runs ORDER BY run_ts DESC LIMIT 1")
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    if int(b["n_entities"]) == 0:
        return {"ok": False, "reason": "A tabela daily_metrics está vazia."}
    try:
        src = _df("SELECT value FROM app_meta WHERE key='source'")
        source = src["value"].iloc[0] if len(src) else None
    except Exception:
        source = None
    st = {"ok": True, "source": source, "n_entities": int(b["n_entities"]),
          "n_series": int(b["n_series"]), "n_rows": int(b["n_rows"]),
          "date_min": str(b["date_min"])[:10], "date_max": str(b["date_max"])[:10],
          "has_run": len(run) > 0}
    if st["has_run"]:
        r = run.iloc[0]
        st.update(run_ts=str(r["run_ts"])[:16], model_version=r["model_version"],
                  stale=str(r["data_max_date"])[:10] < st["date_max"])
    return st


# ------------------------------------------------------------------ aba Dados
TABLES = {
    "daily_metrics": "Série diária por entidade e métrica (dado base).",
    "entities": "Cadastro de entidades (equipamentos, áreas e pontos de monitoramento).",
    "metrics_catalog": "Catálogo de métricas: área, unidade, agregação, limites e referências.",
    "v_outliers": "Resultado do modelo de outlier (última execução).",
    "v_trends": "Resultado do modelo de tendência (última execução).",
    "ml_runs": "Histórico das execuções dos modelos.",
}
_MAX_ROWS = 50_000


def table_columns(table: str) -> list[str]:
    assert table in TABLES
    return _df(f"SELECT * FROM {table} LIMIT 0").columns.tolist()


def date_bounds() -> tuple[str, str]:
    r = _df("SELECT MIN(ref_date) AS a, MAX(ref_date) AS b FROM daily_metrics").iloc[0]
    return str(r["a"])[:10], str(r["b"])[:10]


def entities() -> pd.DataFrame:
    return _df("SELECT entity_id, name, planta, tipo FROM entities ORDER BY name")


def metrics() -> list[str]:
    return _df("SELECT DISTINCT metric FROM daily_metrics ORDER BY 1")["metric"].tolist()


def load_table(table: str, entity_id=None, metric=None, d0=None, d1=None,
               only_outliers=False) -> tuple[pd.DataFrame, int]:
    """Retorna (linhas filtradas, total sem corte). `table` é validada contra TABLES."""
    cols = table_columns(table)
    where, params = [], []
    if entity_id and "entity_id" in cols:
        where.append("t.entity_id = ?"); params.append(entity_id)
    if metric and "metric" in cols:
        where.append("t.metric = ?"); params.append(metric)
    if d0 and d1 and "ref_date" in cols:
        where.append("t.ref_date BETWEEN ? AND ?"); params += [d0, d1]
    if only_outliers and "is_outlier" in cols:
        where.append("t.is_outlier")
    w = ("WHERE " + " AND ".join(where)) if where else ""
    join = ("LEFT JOIN entities e ON e.entity_id = t.entity_id"
            if "entity_id" in cols and table != "entities" else "")
    extra = ", e.name AS ativo, e.planta AS planta" if join else ""
    order = "ORDER BY t.ref_date DESC" if "ref_date" in cols else ""
    total = int(_df(f"SELECT COUNT(*) AS n FROM {table} t {w}", params)["n"].iloc[0])
    df = _df(f"SELECT t.*{extra} FROM {table} t {join} {w} {order} LIMIT {_MAX_ROWS}", params)
    return df, total
