"""Previsão dos próximos dias por série (modelo próprio: sem dependência extra e fácil de auditar).

Componentes
- sazonalidade semanal: desvio médio de cada dia da semana em relação à média móvel de 7 dias (últimas 8 semanas);
- nível: média dos últimos 28 dias sem o efeito do dia da semana (com picos/paradas aparados);
- tendência: só entra se o modelo de tendência (trends.trend_one, janela de 90 dias) a considerar relevante;
  é amortecida (PHI) para a previsão não "disparar" em horizontes maiores;
- faixa de 80%: contagens usam quantis de Poisson; as demais, ruído robusto (MAD) dos últimos 56 dias, que se abre
  levemente com o horizonte.

Cada série é validada com um backtest: o modelo é ajustado sem os últimos BACKTEST_DAYS dias e comparado ao que
aconteceu. WAPE (erro absoluto total / total real) e a cobertura real da faixa ficam gravados junto da previsão.
"""
import numpy as np
import pandas as pd
from scipy import stats

from .trends import trend_one

HORIZON = 14
HISTORY_DAYS = 365
MIN_DAYS = 120
BACKTEST_DAYS = 14
LEVEL = 0.80
PHI = 0.97
_Z = float(stats.norm.ppf(0.5 + LEVEL / 2))


def _winsorize(y: pd.Series) -> pd.Series:
    med = float(np.median(y))
    mad = 1.4826 * float(np.median(np.abs(y - med)))
    return y.clip(med - 4 * mad, med + 4 * mad) if mad > 0 else y


def _forecast(y: pd.Series, metric: str, kind: str, horizon: int, scale: float = 1.0) -> pd.DataFrame:
    """Prevê `horizon` dias após o último dia de y (série diária). `scale` calibra a largura da faixa."""
    tail = y.iloc[-HISTORY_DAYS:]
    recent = _winsorize(tail.iloc[-56:])
    ma = recent.rolling(7, center=True, min_periods=4).mean()
    season = (recent - ma).groupby(recent.index.dayofweek).mean().reindex(range(7)).fillna(0.0)
    season = season - season.mean()
    last28 = _winsorize(tail.iloc[-28:])
    deseason = last28 - season.reindex(last28.index.dayofweek).to_numpy()
    t90 = tail.iloc[-90:]
    slope, _, p, effect = trend_one(t90.to_numpy(), t90.index.dayofweek.to_numpy())
    trend = slope if (p < 0.05 and effect >= 1.0) else 0.0
    level = float(deseason.mean()) + trend * 13.5          # centro da janela de 28 dias -> último dia
    res = recent.to_numpy() - season.reindex(recent.index.dayofweek).to_numpy()
    res = res - np.polyval(np.polyfit(np.arange(len(res)), res, 1), np.arange(len(res)))
    sd = 1.4826 * float(np.median(np.abs(res - np.median(res))))

    last = y.index.max()
    days = pd.date_range(last + pd.Timedelta(days=1), periods=horizon, freq="D")
    h = np.arange(1, horizon + 1)
    damp = np.cumsum(PHI ** h)
    mid = level + trend * damp + season.reindex(days.dayofweek).to_numpy()
    if kind == "contagem":
        lam = np.clip(mid, 0.0, None)
        lo, hi = stats.poisson.ppf((1 - LEVEL) / 2, lam), stats.poisson.ppf(1 - (1 - LEVEL) / 2, lam)
        mid = lam
    else:
        width = _Z * sd * scale * np.sqrt(1 + 0.02 * h)
        lo, hi = mid - width, mid + width
    floor, cap = 0.0, (100.0 if metric.endswith("_pct") else np.inf)
    mid, lo, hi = np.clip(mid, floor, cap), np.clip(lo, floor, cap), np.clip(hi, floor, cap)
    lo, hi = np.minimum(lo, mid), np.maximum(hi, mid)       # faixa discreta (Poisson) sempre contém a previsão
    return pd.DataFrame({"ref_date": days, "horizon_days": h, "yhat": mid, "yhat_lower": lo, "yhat_upper": hi})


def _calibrate(y: pd.Series, metric: str, kind: str) -> float:
    """Fator de largura da faixa: backtest em uma janela ANTERIOR à usada na validação (evita medir no que calibrou)."""
    if kind == "contagem" or len(y) < MIN_DAYS + BACKTEST_DAYS:
        return 1.0
    train, actual = y.iloc[:-2 * BACKTEST_DAYS], y.iloc[-2 * BACKTEST_DAYS:-BACKTEST_DAYS]
    f = _forecast(train, metric, kind, BACKTEST_DAYS)
    sd_h = (f["yhat_upper"] - f["yhat_lower"]).to_numpy() / (2 * _Z)
    r = np.abs(actual.to_numpy() - f["yhat"].to_numpy()) / np.where(sd_h > 0, sd_h, np.nan)
    r = r[np.isfinite(r)]
    return float(np.clip(np.quantile(r, LEVEL) / _Z, 1.0, 4.0)) if len(r) else 1.0


def _backtest(y: pd.Series, metric: str, kind: str, scale: float) -> tuple[float, float]:
    train, actual = y.iloc[:-BACKTEST_DAYS], y.iloc[-BACKTEST_DAYS:]
    if len(train) < MIN_DAYS - BACKTEST_DAYS:
        return np.nan, np.nan
    f = _forecast(train, metric, kind, BACKTEST_DAYS, scale)
    a = actual.to_numpy()
    wape = float(np.abs(a - f["yhat"].to_numpy()).sum() / a.sum() * 100) if a.sum() > 0 else np.nan
    cover = float(((a >= f["yhat_lower"].to_numpy()) & (a <= f["yhat_upper"].to_numpy())).mean() * 100)
    return wape, cover


def detect(metrics: pd.DataFrame, catalog: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    kind = dict(zip(catalog["metric"], catalog["tipo_dado"]))
    newest = metrics["ref_date"].max()
    frames = []
    for (ent, met), g in metrics.groupby(["entity_id", "metric"]):
        s = g.set_index("ref_date")["value"].sort_index()
        s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D")).interpolate(limit=3).dropna()
        if len(s) < MIN_DAYS or s.index.max() < newest - pd.Timedelta(days=3):
            continue
        k = kind.get(met, "continuo")
        scale = _calibrate(s, met, k)
        wape, cover = _backtest(s, met, k, scale)
        f = _forecast(s, met, k, horizon, scale)
        f.insert(0, "metric", met)
        f.insert(0, "entity_id", ent)
        f["wape_pct"], f["coverage_pct"] = wape, cover
        frames.append(f)
    cols = ["entity_id", "metric", "ref_date", "horizon_days", "yhat", "yhat_lower", "yhat_upper",
            "wape_pct", "coverage_pct"]
    return pd.concat(frames, ignore_index=True)[cols] if frames else pd.DataFrame(columns=cols)
