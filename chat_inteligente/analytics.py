"""Consultas das análises (produção, segurança, meio ambiente, ML, detalhe).

Regra de agregação: cada métrica declara no metrics_catalog se agrega por soma
(toneladas, contagens, horas) ou média (taxas, concentrações, intensidades).
A entidade SEG00 é a soma de todas as áreas de segurança: fica fora de rankings e somas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .db import connect

PERIODOS = ["Últimos 30 dias", "Últimos 90 dias", "Últimos 12 meses", "Ano atual", "Todo o período"]
AREAS = {"producao": "Produção", "seguranca": "Segurança", "meio_ambiente": "Meio ambiente"}
AGG = "CASE WHEN c.agregacao = 'soma' THEN SUM(d.value) ELSE AVG(d.value) END"
NOT_CONSOL = "e.tipo NOT LIKE 'consolidado_seguranca'"
_GRAINS = {"day", "week", "month", "quarter", "year"}


def _df(sql: str, params=None) -> pd.DataFrame:
    con = connect(read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()


def _scalar(sql, params=None, default=np.nan):
    v = _df(sql, params).iloc[0, 0]
    return default if v is None or pd.isna(v) else float(v)


# ------------------------------------------------------------------ período
def data_range() -> tuple[pd.Timestamp, pd.Timestamp]:
    r = _df("SELECT MIN(ref_date) AS a, MAX(ref_date) AS b FROM daily_metrics").iloc[0]
    return pd.Timestamp(r["a"]), pd.Timestamp(r["b"])


def resolve_period(label: str) -> dict:
    dmin, dmax = data_range()
    if label == "Últimos 30 dias":
        d0 = dmax - pd.Timedelta(days=29)
    elif label == "Últimos 90 dias":
        d0 = dmax - pd.Timedelta(days=89)
    elif label == "Últimos 12 meses":
        d0 = dmax - pd.Timedelta(days=364)
    elif label == "Ano atual":
        d0 = pd.Timestamp(year=dmax.year, month=1, day=1)
    else:
        d0 = dmin
    days = (dmax - d0).days + 1
    per = {"label": label, "d0": str(d0.date()), "d1": str(dmax.date()), "days": days,
           "p0": None, "p1": None}
    if label != "Todo o período":
        p1 = d0 - pd.Timedelta(days=1)
        p0 = p1 - pd.Timedelta(days=days - 1)
        if p0 >= dmin:
            per.update(p0=str(p0.date()), p1=str(p1.date()))
    return per


def grain_for(days: int) -> str:
    return "day" if days <= 100 else ("week" if days <= 400 else "month")


# ------------------------------------------------------------------ séries e totais
def series(metric: str, d0, d1, grain="month", by="entity", entity_ids=None) -> pd.DataFrame:
    assert grain in _GRAINS
    col = {"entity": "e.name", "planta": "e.planta", "tipo": "e.tipo", "total": "'Total'"}[by]
    where, params = ["d.metric = ?", "d.ref_date BETWEEN ? AND ?"], [metric, d0, d1]
    if entity_ids:
        where.append("d.entity_id IN (" + ",".join("?" * len(entity_ids)) + ")")
        params += list(entity_ids)
    return _df(f"""SELECT date_trunc('{grain}', d.ref_date)::DATE AS periodo, {col} AS grupo,
                   {AGG} AS valor
                   FROM daily_metrics d JOIN entities e USING (entity_id)
                   JOIN metrics_catalog c USING (metric)
                   WHERE {' AND '.join(where)}
                   GROUP BY 1, 2, c.agregacao ORDER BY 1, 2""", params)


def total(metric: str, d0, d1, tipo=None, entity_id=None, exclude_consolidated=True) -> float:
    where, params = ["d.metric = ?", "d.ref_date BETWEEN ? AND ?"], [metric, d0, d1]
    if tipo:
        where.append("e.tipo = ?"); params.append(tipo)
    if entity_id:
        where.append("d.entity_id = ?"); params.append(entity_id)
    if exclude_consolidated:
        where.append(NOT_CONSOL)
    return _scalar(f"""SELECT {AGG} FROM daily_metrics d JOIN entities e USING (entity_id)
                       JOIN metrics_catalog c USING (metric) WHERE {' AND '.join(where)}
                       GROUP BY c.agregacao""", params)


def available_metrics(area: str, entity_id: str | None = None) -> pd.DataFrame:
    where, params = ["c.area = ?"], [area]
    if entity_id:
        where.append("d.entity_id = ?"); params.append(entity_id)
    return _df(f"""SELECT DISTINCT c.metric, c.unidade, c.descricao FROM metrics_catalog c
                   JOIN daily_metrics d USING (metric) WHERE {' AND '.join(where)} ORDER BY 1""", params)


def entities_with(area: str, tipos: list[str] | None = None) -> pd.DataFrame:
    where, params = ["c.area = ?"], [area]
    if tipos:
        where.append("e.tipo IN (" + ",".join("?" * len(tipos)) + ")"); params += tipos
    return _df(f"""SELECT DISTINCT e.entity_id, e.name, e.planta, e.tipo FROM entities e
                   JOIN daily_metrics d USING (entity_id) JOIN metrics_catalog c USING (metric)
                   WHERE {' AND '.join(where)} ORDER BY e.name""", params)


def daily(entity_id: str, metric: str, d0, d1) -> pd.DataFrame:
    return _df("""SELECT ref_date, value FROM daily_metrics
                  WHERE entity_id=? AND metric=? AND ref_date BETWEEN ? AND ? ORDER BY 1""",
               [entity_id, metric, d0, d1])


def metric_info(metric: str) -> dict:
    return _df("SELECT * FROM metrics_catalog WHERE metric=?", [metric]).iloc[0].to_dict()


# ------------------------------------------------------------------ produção
def producao_resumo(d0, d1, p0=None, p1=None) -> pd.DataFrame:
    df = _df("""SELECT e.name AS ativo, e.entity_id, d.ref_date, d.value
                FROM daily_metrics d JOIN entities e USING (entity_id)
                WHERE d.metric='producao_t' AND d.ref_date BETWEEN ? AND ?""", [d0, d1])
    if df.empty:
        return df
    ref = _df("""SELECT entity_id, quantile_cont(value, 0.5) AS mediana_ref FROM daily_metrics
                 WHERE metric='producao_t' AND value > 0 GROUP BY 1""").set_index("entity_id")["mediana_ref"]
    rows = []
    for (ativo, eid), g in df.groupby(["ativo", "entity_id"]):
        v = g["value"]
        parado = (v < 0.25 * ref[eid]).sum()
        rows.append({"ativo": ativo, "total_t": v.sum(), "media_dia": v.mean(), "p10": v.quantile(.1),
                     "mediana": v.median(), "p90": v.quantile(.9), "maximo": v.max(),
                     "dias_parado_ou_reduzido": int(parado),
                     "disponibilidade_dias_pct": 100 * (1 - parado / len(v))})
    out = pd.DataFrame(rows)
    if p0:
        prev = _df("""SELECT e.name AS ativo, SUM(d.value) AS prev FROM daily_metrics d
                      JOIN entities e USING (entity_id)
                      WHERE d.metric='producao_t' AND d.ref_date BETWEEN ? AND ? GROUP BY 1""", [p0, p1])
        out = out.merge(prev, on="ativo", how="left")
        out["variacao_pct"] = (out["total_t"] / out["prev"] - 1) * 100
        out = out.drop(columns="prev")
    return out.round(1)


def paradas(entity_id: str, d0, d1, frac=0.25) -> pd.DataFrame:
    """Períodos consecutivos com produção < frac × mediana histórica."""
    df = daily(entity_id, "producao_t", d0, d1)
    ref = _scalar("SELECT quantile_cont(value,0.5) FROM daily_metrics WHERE entity_id=? "
                  "AND metric='producao_t' AND value>0", [entity_id])
    if df.empty or np.isnan(ref):
        return pd.DataFrame()
    df["baixo"] = df["value"] < frac * ref
    df["grp"] = (df["baixo"] != df["baixo"].shift()).cumsum()
    rows = []
    for _, g in df[df["baixo"]].groupby("grp"):
        rows.append({"inicio": g["ref_date"].min(), "fim": g["ref_date"].max(), "dias": len(g),
                     "perda_estimada_t": round(float((ref - g["value"]).sum()))})
    return pd.DataFrame(rows).sort_values("inicio", ascending=False) if rows else pd.DataFrame()


def yoy(entity_id: str, metric: str) -> pd.DataFrame:
    df = _df(f"""SELECT EXTRACT(year FROM d.ref_date)::INT AS ano, EXTRACT(month FROM d.ref_date)::INT AS mes,
                 {AGG} AS valor FROM daily_metrics d JOIN metrics_catalog c USING (metric)
                 WHERE d.entity_id=? AND d.metric=? GROUP BY 1, 2, c.agregacao""", [entity_id, metric])
    return df.pivot(index="mes", columns="ano", values="valor")


def pair(entity_id: str, m1: str, m2: str, d0, d1) -> pd.DataFrame:
    return _df("""SELECT a.value AS x, b.value AS y FROM daily_metrics a
                  JOIN daily_metrics b ON a.entity_id=b.entity_id AND a.ref_date=b.ref_date
                  WHERE a.entity_id=? AND a.metric=? AND b.metric=? AND a.ref_date BETWEEN ? AND ?""",
               [entity_id, m1, m2, d0, d1]).rename(columns={"x": m1, "y": m2})


# ------------------------------------------------------------------ segurança
SEG_METRICS = ["desvios", "ocorrencias", "incidentes", "acidentes"]


def seguranca_totais(d0, d1, entity_ids=None) -> pd.DataFrame:
    """Linhas = área, colunas = 4 métricas + HH + taxa de acidentes por milhão de HH."""
    where, params = [NOT_CONSOL, "d.ref_date BETWEEN ? AND ?"], [d0, d1]
    if entity_ids:
        where.append("d.entity_id IN (" + ",".join("?" * len(entity_ids)) + ")"); params += list(entity_ids)
    df = _df(f"""SELECT e.name AS area, d.metric, SUM(d.value) AS v FROM daily_metrics d
                 JOIN entities e USING (entity_id)
                 WHERE d.metric IN ('desvios','ocorrencias','incidentes','acidentes','horas_homem_trabalhadas')
                 AND {' AND '.join(where)} GROUP BY 1, 2""", params)
    w = df.pivot(index="area", columns="metric", values="v").fillna(0)
    w["taxa_acidentes_por_milhao_hh"] = w["acidentes"] * 1e6 / w["horas_homem_trabalhadas"].replace(0, np.nan)
    return w.reset_index()


def seguranca_anual_taxa() -> pd.DataFrame:
    df = _df("""SELECT e.name AS area, EXTRACT(year FROM d.ref_date)::INT AS ano,
                SUM(d.value) FILTER (WHERE d.metric='acidentes') * 1e6 /
                NULLIF(SUM(d.value) FILTER (WHERE d.metric='horas_homem_trabalhadas'), 0) AS taxa
                FROM daily_metrics d JOIN entities e USING (entity_id)
                WHERE d.metric IN ('acidentes','horas_homem_trabalhadas') GROUP BY 1, 2""")
    return df


def dias_sem_acidente() -> pd.DataFrame:
    df = _df(f"""SELECT e.name AS area, d.ref_date, d.value FROM daily_metrics d
                 JOIN entities e USING (entity_id)
                 WHERE d.metric='acidentes' AND {NOT_CONSOL} ORDER BY 1, 2""")
    dmax = data_range()[1]
    rows = []
    for area, g in df.groupby("area"):
        hits = g.loc[g["value"] > 0, "ref_date"]
        last = pd.Timestamp(hits.max()) if len(hits) else None
        gaps = pd.to_datetime(hits).sort_values().diff().dt.days.dropna()
        first = pd.Timestamp(g["ref_date"].min())
        longest = max([int(gaps.max()) if len(gaps) else 0,
                       (pd.Timestamp(hits.min()) - first).days if len(hits) else (dmax - first).days,
                       (dmax - last).days if last is not None else 0])
        rows.append({"area": area, "ultimo_acidente": None if last is None else last.date(),
                     "dias_sem_acidente": (dmax - last).days if last is not None else (dmax - first).days,
                     "maior_sequencia_dias": longest, "acidentes_total": int(hits.shape[0])})
    return pd.DataFrame(rows).sort_values("dias_sem_acidente")


def padrao_semanal(metric: str, d0, d1) -> pd.DataFrame:
    df = _df(f"""SELECT EXTRACT(dow FROM d.ref_date)::INT AS dow, AVG(d.value) AS media FROM daily_metrics d
                 JOIN entities e USING (entity_id) WHERE d.metric=? AND {NOT_CONSOL}
                 AND d.ref_date BETWEEN ? AND ? GROUP BY 1 ORDER BY 1""", [metric, d0, d1])
    names = {0: "dom", 1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex", 6: "sáb"}
    df["dia"] = df["dow"].map(names)
    return df


def acidentes_recentes(d0, d1, limit=25) -> pd.DataFrame:
    return _df(f"""SELECT d.ref_date AS data, e.name AS area, e.planta, d.value AS acidentes
                   FROM daily_metrics d JOIN entities e USING (entity_id)
                   WHERE d.metric='acidentes' AND d.value > 0 AND {NOT_CONSOL}
                   AND d.ref_date BETWEEN ? AND ? ORDER BY 1 DESC LIMIT ?""", [d0, d1, limit])


# ------------------------------------------------------------------ meio ambiente
_FORA = ("(c.limite_superior IS NOT NULL AND d.value > c.limite_superior) "
         "OR (c.limite_inferior IS NOT NULL AND d.value < c.limite_inferior)")


def conformidade(d0, d1) -> pd.DataFrame:
    return _df(f"""SELECT e.name AS ponto, d.metric AS metrica, c.unidade, c.limite_inferior, c.limite_superior,
                   COUNT(*) AS medicoes, COUNT(*) FILTER (WHERE {_FORA}) AS fora_do_limite,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE {_FORA}) / COUNT(*), 2) AS pct_fora,
                   ROUND(AVG(d.value), 3) AS media, ROUND(MAX(d.value), 3) AS maximo,
                   ROUND(MIN(d.value), 3) AS minimo
                   FROM daily_metrics d JOIN entities e USING (entity_id) JOIN metrics_catalog c USING (metric)
                   WHERE c.area='meio_ambiente' AND (c.limite_superior IS NOT NULL OR c.limite_inferior IS NOT NULL)
                   AND d.ref_date BETWEEN ? AND ?
                   GROUP BY 1, 2, 3, 4, 5 ORDER BY pct_fora DESC, 1, 2""", [d0, d1])


def excedencias(d0, d1, limit=200) -> pd.DataFrame:
    return _df(f"""SELECT d.ref_date AS data, e.name AS ponto, d.metric AS metrica, d.value AS valor,
                   c.limite_inferior, c.limite_superior, c.unidade
                   FROM daily_metrics d JOIN entities e USING (entity_id) JOIN metrics_catalog c USING (metric)
                   WHERE c.area='meio_ambiente' AND ({_FORA}) AND d.ref_date BETWEEN ? AND ?
                   ORDER BY 1 DESC, 2 LIMIT ?""", [d0, d1, limit])


def sazonalidade(entity_id: str, metric: str) -> pd.DataFrame:
    return _df("""SELECT EXTRACT(month FROM ref_date)::INT AS mes, AVG(value) AS media
                  FROM daily_metrics WHERE entity_id=? AND metric=? GROUP BY 1 ORDER BY 1""",
               [entity_id, metric])


# worldsteel Sustainability Indicators 2024 (média global; BF-BOF para CO2 e energia)
REF_WORLDSTEEL = {
    "intensidade_co2_t_t": ("tCO2/t aço", 2.34, "worldsteel 2024, rota alto-forno/aciaria"),
    "consumo_energia_gj_t": ("GJ/t aço", 23.88, "worldsteel 2024, rota alto-forno/aciaria"),
    "intensidade_particulados_kg_t": ("kg/t aço", 0.32, "worldsteel 2024, média global"),
    "intensidade_sox_kg_t": ("kg/t aço", 0.64, "worldsteel 2024, média global"),
    "intensidade_nox_kg_t": ("kg/t aço", 0.66, "worldsteel 2024, média global"),
    "consumo_agua_m3_t": ("m³/t aço", 8.50, "worldsteel 2024, captação média global"),
}


# ------------------------------------------------------------------ ML
def ml_kpis(dmax) -> dict:
    d7 = str((pd.Timestamp(dmax) - pd.Timedelta(days=6)).date())
    d90 = str((pd.Timestamp(dmax) - pd.Timedelta(days=89)).date())
    return {
        "outliers_7d": int(_scalar("SELECT COUNT(*) FROM v_outliers WHERE is_outlier AND ref_date >= ?", [d7], 0)),
        "outliers_90d": int(_scalar("SELECT COUNT(*) FROM v_outliers WHERE is_outlier AND ref_date >= ?", [d90], 0)),
        "outliers_total": int(_scalar("SELECT COUNT(*) FROM v_outliers WHERE is_outlier", None, 0)),
        "alta_90": int(_scalar("SELECT COUNT(*) FROM v_trends WHERE window_days=90 AND trend_direction='alta'", None, 0)),
        "queda_90": int(_scalar("SELECT COUNT(*) FROM v_trends WHERE window_days=90 AND trend_direction='queda'", None, 0)),
    }


def outliers_table(d0, d1, area=None, planta=None, limit=300) -> pd.DataFrame:
    where, params = ["o.is_outlier", "o.ref_date BETWEEN ? AND ?"], [d0, d1]
    if area:
        where.append("c.area = ?"); params.append(area)
    if planta:
        where.append("e.planta = ?"); params.append(planta)
    return _df(f"""SELECT o.ref_date AS data, e.name AS ativo, e.planta, c.area, o.metric AS metrica,
                   ROUND(o.value, 2) AS observado, ROUND(o.expected, 2) AS esperado,
                   ROUND(o.score, 1) AS score,
                   CASE WHEN o.score > 0 THEN 'acima' ELSE 'abaixo' END AS direcao
                   FROM v_outliers o JOIN entities e USING (entity_id) JOIN metrics_catalog c USING (metric)
                   WHERE {' AND '.join(where)}
                   ORDER BY o.ref_date DESC, ABS(o.score) DESC LIMIT ?""", params + [limit])


def outliers_por_mes(area=None) -> pd.DataFrame:
    where, params = ["o.is_outlier"], []
    if area:
        where.append("c.area = ?"); params.append(area)
    return _df(f"""SELECT date_trunc('month', o.ref_date)::DATE AS mes, c.area, COUNT(*) AS outliers
                   FROM v_outliers o JOIN metrics_catalog c USING (metric)
                   WHERE {' AND '.join(where)} GROUP BY 1, 2 ORDER BY 1, 2""", params)


def outliers_por_entidade(d0, d1) -> pd.DataFrame:
    return _df("""SELECT e.name AS ativo, COUNT(*) AS outliers FROM v_outliers o
                  JOIN entities e USING (entity_id)
                  WHERE o.is_outlier AND o.ref_date BETWEEN ? AND ? GROUP BY 1 ORDER BY 2 DESC LIMIT 15""",
               [d0, d1])


def trends_table(window: int, area=None, planta=None, directions=None) -> pd.DataFrame:
    where, params = ["t.window_days = ?"], [window]
    if area:
        where.append("c.area = ?"); params.append(area)
    if planta:
        where.append("e.planta = ?"); params.append(planta)
    if directions:
        where.append("t.trend_direction IN (" + ",".join("?" * len(directions)) + ")"); params += list(directions)
    return _df(f"""SELECT e.name AS ativo, e.planta, c.area, t.metric AS metrica,
                   t.trend_direction AS tendencia, ROUND(t.pct_change, 1) AS variacao_pct,
                   ROUND(t.slope_per_day, 4) AS inclinacao_dia, ROUND(t.p_value, 4) AS p_valor
                   FROM v_trends t JOIN entities e USING (entity_id) JOIN metrics_catalog c USING (metric)
                   WHERE {' AND '.join(where)}
                   ORDER BY ABS(COALESCE(t.pct_change, 0)) DESC""", params)


def trends_matrix() -> pd.DataFrame:
    return _df("""SELECT c.area, t.window_days AS janela, t.trend_direction AS tendencia, COUNT(*) AS series
                  FROM v_trends t JOIN metrics_catalog c USING (metric)
                  GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""")


def series_trends(entity_id: str, metric: str) -> pd.DataFrame:
    return _df("""SELECT window_days AS janela, trend_direction AS tendencia, ROUND(pct_change,1) AS variacao_pct,
                  ROUND(slope_per_day,4) AS inclinacao_dia, ROUND(p_value,4) AS p_valor
                  FROM v_trends WHERE entity_id=? AND metric=? ORDER BY 1""", [entity_id, metric])


def series_outliers(entity_id: str, metric: str, d0, d1) -> pd.DataFrame:
    return _df("""SELECT ref_date AS data, ROUND(value,2) AS observado, ROUND(expected,2) AS esperado,
                  ROUND(score,1) AS score FROM v_outliers
                  WHERE entity_id=? AND metric=? AND is_outlier AND ref_date BETWEEN ? AND ?
                  ORDER BY 1 DESC""", [entity_id, metric, d0, d1])


def expected_series(entity_id: str, metric: str, d0, d1) -> pd.DataFrame:
    return _df("""SELECT ref_date, expected FROM v_outliers WHERE entity_id=? AND metric=?
                  AND ref_date BETWEEN ? AND ? ORDER BY 1""", [entity_id, metric, d0, d1])
