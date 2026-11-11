"""Tendência por série e janela (30, 90 e 365 dias).

Regressão linear sobre a série sem efeito do dia da semana; o p-valor corrige a
autocorrelação (tamanho efetivo da amostra). Só é "relevante" (alta/queda) se
p < 0.05 E a variação ao longo da janela (inclinação x dias) for >= MIN_EFFECT desvios-padrão
do ruído da série. Isso funciona igual para pH, toneladas ou acidentes (independe da escala).
Contagens esparsas (< MIN_EVENTS eventos na janela) não recebem tendência.
"""
import numpy as np
import pandas as pd
from scipy import stats

WINDOWS = (30, 90, 365)
ALPHA = 0.05
MIN_EFFECT = 1.0
MIN_EVENTS = 10


def trend_one(y: np.ndarray, dow: np.ndarray):
    n = len(y)
    med = np.median(y)
    mad = 1.4826 * np.median(np.abs(y - med))
    if mad > 0:                                    # paradas/picos isolados não ditam a tendência
        y = np.clip(y, med - 4 * mad, med + 4 * mad)
    y = y - pd.Series(y).groupby(dow).transform("mean").to_numpy() + y.mean()   # tira padrão semanal
    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    res = y - (intercept + slope * x)
    rho = np.corrcoef(res[1:], res[:-1])[0, 1] if n > 4 and res.std() > 0 else 0.0
    rho = float(np.clip(np.nan_to_num(rho), 0, 0.95))
    n_eff = max(n * (1 - rho) / (1 + rho), 5.0)
    sxx = np.sum((x - x.mean()) ** 2)
    se = np.sqrt(np.sum(res ** 2) / max(n - 2, 1) / sxx) * np.sqrt((n - 2) / (n_eff - 2))
    p = 1.0 if se == 0 else float(2 * stats.t.sf(abs(slope) / se, df=n_eff - 2))
    k = max(7, int(0.25 * n))
    first, last = y[:k].mean(), y[-k:].mean()
    pct = (last - first) / abs(first) * 100 if abs(first) > 1e-9 else np.nan
    resid_sd = res.std()
    effect = abs(slope) * (n - 1) / resid_sd if resid_sd > 0 else 0.0
    return slope, pct, p, effect


def detect(metrics: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    kind = dict(zip(catalog["metric"], catalog["tipo_dado"]))
    rows = []
    for (ent, met), g in metrics.groupby(["entity_id", "metric"]):
        s = g.set_index("ref_date")["value"].sort_index()
        s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
        last = s.index.max()
        for w in WINDOWS:
            tail = s[s.index > last - pd.Timedelta(days=w)].dropna()
            if len(tail) < max(14, w // 2):
                continue
            if kind.get(met) == "contagem" and tail.sum() < MIN_EVENTS:
                continue
            slope, pct, p, effect = trend_one(tail.to_numpy(), tail.index.dayofweek.to_numpy())
            sig = bool(p < ALPHA and effect >= MIN_EFFECT)
            direction = "estavel" if not sig else ("alta" if slope > 0 else "queda")
            rows.append((ent, met, w, slope, pct, p, direction, sig))
    return pd.DataFrame(rows, columns=[
        "entity_id", "metric", "window_days", "slope_per_day", "pct_change",
        "p_value", "trend_direction", "is_significant"])
