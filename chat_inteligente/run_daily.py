"""Job diário: rodar APÓS a atualização das tabelas base.
Uso: python -m chat_inteligente.run_daily
"""
import logging
import time
import uuid
from datetime import datetime

from .db import connect, init_schema
from .ml import forecast, outliers, trends

MODEL_VERSION = "poisson+robust-z+linreg+seasonal-forecast-v4"
KEEP_RUNS = 30   # execuções antigas são removidas para o banco não crescer sem limite
logger = logging.getLogger(__name__)


def main() -> str:
    started = time.perf_counter()
    con = connect()
    in_transaction = False
    try:
        init_schema(con)
        metrics = con.execute("SELECT * FROM daily_metrics").df()
        catalog = con.execute("SELECT * FROM metrics_catalog").df()
        metrics["ref_date"] = metrics["ref_date"].astype("datetime64[ns]")
        metrics = metrics.dropna(subset=["value"])
        keys = ["entity_id", "metric", "ref_date"]
        dups = int(metrics.duplicated(keys).sum())
        if dups:   # dado real sujo: mais de um valor no mesmo dia derrubaria os modelos; usa a média e avisa
            logger.warning("daily_metrics tem %d linha(s) duplicada(s) por (entidade, métrica, dia): usando a média.", dups)
            metrics = metrics.groupby(keys, as_index=False)["value"].mean()
        run_id = uuid.uuid4().hex[:12]
        step = time.perf_counter()
        out = outliers.detect(metrics, catalog)
        out_secs = time.perf_counter() - step
        step = time.perf_counter()
        tr = trends.detect(metrics, catalog)
        trend_secs = time.perf_counter() - step
        step = time.perf_counter()
        fc = forecast.detect(metrics, catalog)
        forecast_secs = time.perf_counter() - step
        out.insert(0, "run_id", run_id)
        tr.insert(0, "run_id", run_id)
        fc.insert(0, "run_id", run_id)
        fc["ref_date"] = fc["ref_date"].dt.date
        out["ref_date"] = out["ref_date"].dt.date
        con.execute("BEGIN")
        in_transaction = True
        con.execute("INSERT INTO ml_outliers SELECT * FROM out")
        con.execute("INSERT INTO ml_trends SELECT * FROM tr")
        con.execute("INSERT INTO ml_forecasts SELECT * FROM fc")
        con.execute("INSERT INTO ml_runs VALUES (?,?,?,?,?,?)", [
            run_id, datetime.now(), MODEL_VERSION, metrics["ref_date"].max().date(),
            metrics.groupby(["entity_id", "metric"]).ngroups, int(out["is_outlier"].sum())])
        old = f"(SELECT run_id FROM ml_runs ORDER BY run_ts DESC OFFSET {KEEP_RUNS})"
        con.execute(f"DELETE FROM ml_outliers WHERE run_id IN {old}")
        con.execute(f"DELETE FROM ml_trends WHERE run_id IN {old}")
        con.execute(f"DELETE FROM ml_forecasts WHERE run_id IN {old}")
        con.execute(f"DELETE FROM ml_runs WHERE run_id IN {old}")
        con.execute("COMMIT")
        in_transaction = False
        logger.info("Modelos concluídos run_id=%s séries=%d outliers=%.2fs tendências=%.2fs previsões=%.2fs total=%.2fs",
                    run_id, metrics.groupby(["entity_id", "metric"]).ngroups, out_secs, trend_secs,
                    forecast_secs, time.perf_counter() - started)
        return run_id
    except Exception:
        if in_transaction:
            con.execute("ROLLBACK")
        logger.exception("Falha na execução dos modelos após %.2fs", time.perf_counter() - started)
        raise
    finally:
        con.close()


if __name__ == "__main__":
    print("run_id:", main())
