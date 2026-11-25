"""Gráficos da diretoria (Altair): esperado x observado, outliers destacados, faixa de previsão e limites."""
import altair as alt
import pandas as pd

ACCENT, MUTED, ALERT, LIMIT = "#1f5f8b", "#9aa4b2", "#d64545", "#e0a21b"
_DATE_AXIS = alt.Axis(format="%d/%m/%y", title=None, labelOverlap=True, grid=False)


def _base(df: pd.DataFrame, height: int) -> alt.Chart:
    df = df.copy()
    if "ref_date" in df:
        df["ref_date"] = pd.to_datetime(df["ref_date"])
    return alt.Chart(df).properties(height=height)


def series_chart(obs: pd.DataFrame, expected: pd.DataFrame | None = None, outliers: pd.DataFrame | None = None,
                 forecast: pd.DataFrame | None = None, unit: str = "", limits: tuple = (None, None),
                 height: int = 320) -> alt.Chart:
    """obs: ref_date,value · expected: ref_date,expected · outliers: ref_date,value · forecast: ref_date,yhat,yhat_lower,yhat_upper."""
    y_title = unit or None
    x = alt.X("ref_date:T", axis=_DATE_AXIS)
    tip_d = alt.Tooltip("ref_date:T", title="Data", format="%d/%m/%Y")
    layers = []
    if forecast is not None and len(forecast):
        f = forecast.copy()
        layers.append(_base(f, height).mark_area(color=ACCENT, opacity=0.14).encode(
            x=x, y=alt.Y("yhat_lower:Q", title=y_title), y2="yhat_upper:Q"))
        layers.append(_base(f, height).mark_line(color=ACCENT, strokeDash=[6, 4], strokeWidth=2).encode(
            x=x, y="yhat:Q", tooltip=[tip_d, alt.Tooltip("yhat:Q", title="Previsto", format=",.2f"),
                                      alt.Tooltip("yhat_lower:Q", title="Mínimo provável", format=",.2f"),
                                      alt.Tooltip("yhat_upper:Q", title="Máximo provável", format=",.2f")]))
    if expected is not None and len(expected):
        layers.append(_base(expected, height).mark_line(color=MUTED, strokeDash=[3, 3]).encode(
            x=x, y=alt.Y("expected:Q", title=y_title), tooltip=[tip_d, alt.Tooltip("expected:Q", title="Esperado", format=",.2f")]))
    layers.append(_base(obs, height).mark_line(color=ACCENT, strokeWidth=1.6).encode(
        x=x, y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=False)),
        tooltip=[tip_d, alt.Tooltip("value:Q", title="Observado", format=",.2f")]))
    if outliers is not None and len(outliers):
        layers.append(_base(outliers, height).mark_point(color=ALERT, filled=True, size=70).encode(
            x=x, y="value:Q", tooltip=[tip_d, alt.Tooltip("value:Q", title="Fora do padrão", format=",.2f")]))
    for lim, name in zip(limits, ("Limite inferior", "Limite superior")):
        if lim is not None and pd.notna(lim):
            layers.append(alt.Chart(pd.DataFrame({"v": [float(lim)], "n": [name]})).mark_rule(color=LIMIT, strokeDash=[5, 3]).encode(
                y="v:Q", tooltip=[alt.Tooltip("n:N", title=" "), alt.Tooltip("v:Q", title="Valor", format=",.2f")]))
    return alt.layer(*layers).interactive(bind_y=False)


def band_chart(df: pd.DataFrame, x: str, mid: str, lo: str, hi: str, height: int = 280) -> alt.Chart:
    """Previsão com faixa a partir de colunas já nomeadas (ex.: 'Produção prevista (t)', 'Mínimo provável (t)')."""
    d = df[[x, mid, lo, hi]].copy()
    d.columns = ["x", "mid", "lo", "hi"]
    ax = alt.X("x:T", axis=_DATE_AXIS) if pd.api.types.is_datetime64_any_dtype(d["x"]) else alt.X("x:O", title=None)
    tip = [alt.Tooltip("x", title="Data"), alt.Tooltip("mid:Q", title=mid, format=",.2f"),
           alt.Tooltip("lo:Q", title=lo, format=",.2f"), alt.Tooltip("hi:Q", title=hi, format=",.2f")]
    area = alt.Chart(d).mark_area(color=ACCENT, opacity=0.15).encode(x=ax, y=alt.Y("lo:Q", title=None, scale=alt.Scale(zero=False)), y2="hi:Q")
    line = alt.Chart(d).mark_line(color=ACCENT, strokeWidth=2.2, point=True).encode(x=ax, y="mid:Q", tooltip=tip)
    return (area + line).properties(height=height)


def find_band(df: pd.DataFrame):
    """Detecta (x, meio, mínimo, máximo) em um resultado com faixa de previsão. None se não houver."""
    time_col = next((c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])), None)
    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    # Exige semântica de previsão; "limite inferior/superior" pode ser apenas limite ambiental.
    mid = [c for c in nums if str(c).lower() == "yhat" or any(
        k in str(c).lower() for k in ("previs", "prev ", "prev(", "prev_"))]
    low = [c for c in nums if "yhat_lower" in str(c).lower()
           or any(k in str(c).lower() for k in ("mín", "min", "lower"))]
    high = [c for c in nums if "yhat_upper" in str(c).lower()
            or any(k in str(c).lower() for k in ("máx", "max", "upper"))]
    if time_col and low and high and mid:
        return time_col, mid[0], low[0], high[0]
    return None
