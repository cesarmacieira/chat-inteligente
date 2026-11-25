"""Resumo do dia para a diretoria: pontos de atenção calculados direto das tabelas dos modelos (sem LLM, sem custo)."""
import pandas as pd

from . import analytics as A
from .context import fmt_num
from .labels import rotulo

TAGS = {"outlier": "Fora do padrão", "tendencia": "Tendência", "previsao": "Previsão", "limite": "Limite ambiental"}


def build(max_items: int = 6) -> dict:
    """Retorna {'date': 'dd/mm/aaaa', 'items': [(tag, texto), ...]} ou itens vazios se algo falhar."""
    try:
        dmax = A.data_range()[1]
        items: list[tuple[str, str]] = []
        o = A._df(f"""SELECT e.name, o.metric, o.ref_date, o.value, o.expected, o.score
                      FROM v_outliers o JOIN entities e USING (entity_id)
                      WHERE o.is_outlier AND {A.NOT_CONSOL} AND o.ref_date > CAST(? AS DATE) - INTERVAL 3 DAY
                      ORDER BY ABS(o.score) DESC LIMIT 3""", [str(dmax.date())])
        for r in o.itertuples():
            items.append(("outlier", f"{r.name}: em {pd.Timestamp(r.ref_date):%d/%m/%Y}, {rotulo(r.metric)} ficou em "
                                     f"{fmt_num(r.value)}, {'acima' if r.value > r.expected else 'abaixo'} do esperado "
                                     f"({fmt_num(r.expected)})."))
        e = A._df(f"""SELECT e.name, c.metric, COUNT(*) AS dias FROM daily_metrics d
                      JOIN entities e USING (entity_id) JOIN metrics_catalog c USING (metric)
                      WHERE c.area = 'meio_ambiente' AND d.ref_date > CAST(? AS DATE) - INTERVAL 7 DAY
                        AND ((c.limite_superior IS NOT NULL AND d.value > c.limite_superior)
                          OR (c.limite_inferior IS NOT NULL AND d.value < c.limite_inferior))
                      GROUP BY 1, 2 ORDER BY dias DESC LIMIT 2""", [str(dmax.date())])
        for r in e.itertuples():
            items.append(("limite", f"{r.name}: {rotulo(r.metric)} ficou fora do limite em {int(r.dias)} dia(s) "
                                    "da última semana."))
        t = A._df(f"""SELECT e.name, t.metric, t.trend_direction, t.pct_change FROM v_trends t
                      JOIN entities e USING (entity_id)
                      WHERE t.window_days = 90 AND t.trend_direction IN ('alta', 'queda') AND {A.NOT_CONSOL}
                      ORDER BY ABS(COALESCE(t.pct_change, 0)) DESC LIMIT 2""")
        for r in t.itertuples():
            pc = "" if pd.isna(r.pct_change) else f" ({'+' if r.pct_change > 0 else '-'}{fmt_num(abs(r.pct_change), 1)}%)"
            items.append(("tendencia", f"{r.name}: {rotulo(r.metric)} em {r.trend_direction}{pc} nos últimos 90 dias."))
        f = A.forecast_overview(days=7, limit=2)
        for r in f.itertuples():
            if pd.notna(r.variacao_pct) and abs(r.variacao_pct) >= 3:
                items.append(("previsao", f"{r.ativo}: {rotulo(r.metrica)} deve ficar "
                                          f"{fmt_num(abs(r.variacao_pct), 1)}% {'acima' if r.variacao_pct > 0 else 'abaixo'} "
                                          "da média da última semana nos próximos 7 dias."))
        order = {"outlier": 0, "limite": 1, "tendencia": 2, "previsao": 3}
        items.sort(key=lambda x: order[x[0]])
        return {"date": f"{dmax:%d/%m/%Y}", "items": items[:max_items]}
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Não foi possível montar o resumo do dia")
        return {"date": "", "items": []}
