"""Job diário: rodar APÓS a atualização das tabelas base.
Uso: python -m chat_inteligente.run_daily
"""
import uuid
from datetime import datetime

from .db import connect, init_schema
from .ml import outliers, trends

MODEL_VERSION = "poisson+robust-z+linreg-v3"
KEEP_RUNS = 30   # execuções antigas são removidas para o banco não crescer sem limite


def main() -> str:
    con = connect()
    init_schema(con)
    metrics = con.execute("SELECT * FROM daily_metrics").df()
    catalog = con.execute("SELECT * FROM metrics_catalog").df()
    metrics["ref_date"] = metrics["ref_date"].astype("datetime64[ns]")
    run_id = uuid.uuid4().hex[:12]
    out = outliers.detect(metrics, catalog)
    tr = trends.detect(metrics, catalog)
    out.insert(0, "run_id", run_id)
    tr.insert(0, "run_id", run_id)
    out["ref_date"] = out["ref_date"].dt.date
    con.execute("BEGIN")
    con.execute("INSERT INTO ml_outliers SELECT * FROM out")
    con.execute("INSERT INTO ml_trends SELECT * FROM tr")
    con.execute("INSERT INTO ml_runs VALUES (?,?,?,?,?,?)", [
        run_id, datetime.now(), MODEL_VERSION, metrics["ref_date"].max().date(),
        metrics.groupby(["entity_id", "metric"]).ngroups, int(out["is_outlier"].sum())])
    old = f"(SELECT run_id FROM ml_runs ORDER BY run_ts DESC OFFSET {KEEP_RUNS})"
    con.execute(f"DELETE FROM ml_outliers WHERE run_id IN {old}")
    con.execute(f"DELETE FROM ml_trends WHERE run_id IN {old}")
    con.execute(f"DELETE FROM ml_runs WHERE run_id IN {old}")
    con.execute("COMMIT")
    con.close()
    return run_id


if __name__ == "__main__":
    print("run_id:", main())
