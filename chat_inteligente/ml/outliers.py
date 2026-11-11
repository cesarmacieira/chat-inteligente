"""Detecção de outliers por série diária.

- Contínuas (produção, emissões, pH...): esperado = mediana dos mesmos dias da semana nas
  últimas 8 semanas (respeita padrão semanal); escala = MAD móvel dos resíduos passados.
- Contagens (acidentes, desvios...): esperado = média móvel (λ) ajustada por dia da semana;
  score = z equivalente da cauda de Poisson (raro = score alto, sem falso alarme em zeros).
Só usa o passado de cada dia (sem vazamento de futuro).
"""
import warnings

import numpy as np
import pandas as pd
from scipy.stats import norm, poisson

THRESHOLD = 3.5
LOOKBACK_DAYS = 90        # últimos N dias são salvos por completo (para gráficos)
DOW_LAGS = [7 * k for k in range(1, 9)]
SIGMA_WINDOW = 56
MIN_LAMBDA = 0.005


def _nan_stat(fn, mat, min_count):
    cnt = np.sum(~np.isnan(mat), axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        out = fn(mat, axis=0)
    return np.where(cnt >= min_count, out, np.nan)


def score_continuous(s: pd.Series) -> pd.DataFrame:
    lags = np.vstack([s.shift(k).to_numpy() for k in DOW_LAGS])
    expected = _nan_stat(np.nanmedian, lags, 4)
    resid = s.to_numpy() - expected
    sigma = 1.4826 * pd.Series(np.abs(resid), index=s.index).shift(1).rolling(
        SIGMA_WINDOW, min_periods=21).median().to_numpy()
    sigma = np.maximum(sigma, 0.01 * np.abs(expected))
    sigma = np.where(sigma > 0, sigma, np.nan)
    return pd.DataFrame({"expected": expected, "score": resid / sigma}, index=s.index)


def score_count(s: pd.Series) -> pd.DataFrame:
    x = s.to_numpy()
    past = s.shift(1)
    m90 = past.rolling(90, min_periods=30).mean().to_numpy()
    m182 = past.rolling(182, min_periods=60).mean().to_numpy()
    lags = np.vstack([s.shift(7 * k).to_numpy() for k in range(1, 27)])
    dow_mean = _nan_stat(np.nanmean, lags, 8)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        factor = np.where(m182 >= 2, np.clip(dow_mean / m182, 0.5, 1.5), 1.0)
    factor = np.nan_to_num(factor, nan=1.0)
    lam = np.maximum(m90 * factor, MIN_LAMBDA)
    p_up = poisson.sf(x - 1, lam)
    p_lo = poisson.cdf(x, lam)
    z = np.where(x >= lam, norm.isf(np.minimum(p_up, 0.5)), norm.ppf(np.minimum(p_lo, 0.5)))
    return pd.DataFrame({"expected": lam, "score": np.clip(z, -8, 8)}, index=s.index)


def detect(metrics: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    kind = dict(zip(catalog["metric"], catalog["tipo_dado"]))
    cutoff = metrics["ref_date"].max() - pd.Timedelta(days=LOOKBACK_DAYS)
    parts = []
    for (ent, met), g in metrics.groupby(["entity_id", "metric"]):
        s = g.set_index("ref_date")["value"].sort_index()
        s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
        sc = score_count(s) if kind.get(met) == "contagem" else score_continuous(s)
        df = sc.assign(value=s).dropna(subset=["value", "score"])
        df["is_outlier"] = df["score"].abs() >= THRESHOLD
        df = df[df["is_outlier"] | (df.index > cutoff)]
        df.index.name = "ref_date"
        df = df.reset_index()
        df["entity_id"], df["metric"] = ent, met
        parts.append(df)
    out = pd.concat(parts, ignore_index=True)
    return out[["entity_id", "metric", "ref_date", "value", "expected", "score", "is_outlier"]]
