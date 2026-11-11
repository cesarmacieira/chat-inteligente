"""Contexto extra para as respostas: o que as métricas citadas na consulta significam
(unidade, limites) e o que os modelos de ML dizem sobre elas (tendências e outliers recentes).
"""
import re

import pandas as pd

from .db import connect

_NOT_CONSOL = "e.tipo NOT LIKE 'consolidado_seguranca'"


def fmt_num(v, nd: int = 2) -> str:
    """Número no padrão pt-BR (milhar com ponto, decimal com vírgula)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    s = f"{v:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def metrics_in_sql(sql: str, known) -> list[str]:
    low = sql.lower()
    found: list[str] = []
    for m in known:
        if m not in found and re.search(rf"\b{re.escape(str(m).lower())}\b", low):
            found.append(m)
    return found[:3]


def entity_names_in(df, known) -> list[str]:
    """Nomes de ativos que aparecem como valor em colunas de texto do resultado."""
    if df is None or df.empty:
        return []
    vals = set()
    for c in df.columns:
        if df[c].dtype == object:
            vals |= set(df[c].dropna().astype(str).head(200))
    return [n for n in known if n in vals]


def build(sql: str, df=None, friendly: bool = False) -> list[str]:
    """Linhas de contexto (texto pt-BR) para as métricas citadas no SQL. Vazio se algo falhar.
    Se o resultado (df) citar ativos pelo nome, o contexto fica restrito a eles.
    friendly=True devolve só "pontos de atenção" (tendências e outliers) em linguagem de negócio."""
    from .labels import rotulo
    try:
        con = connect(read_only=True)
    except Exception:
        return []
    try:
        cat = con.execute("SELECT * FROM metrics_catalog").df()
        hoje = con.execute("SELECT MAX(ref_date) FROM daily_metrics").fetchone()[0]
        lines: list[str] = []
        known = con.execute("SELECT name FROM entities").df()["name"].tolist()
        names = entity_names_in(df, known)
        ef, ep = ("", [])
        if names:
            ef, ep = " AND e.name IN (" + ",".join("?" * len(names)) + ")", names
        for m in metrics_in_sql(sql, cat["metric"]):
            r = cat[cat["metric"] == m].iloc[0]
            lim = []
            if pd.notna(r["limite_superior"]):
                lim.append(f"limite máximo {fmt_num(r['limite_superior'])}")
            if pd.notna(r["limite_inferior"]):
                lim.append(f"limite mínimo {fmt_num(r['limite_inferior'])}")
            if not friendly:
                lines.append(f"{m}: {r['descricao']} (unidade: {r['unidade']}; agregação: {r['agregacao']}"
                             + (f"; {', '.join(lim)}" if lim else "") + ")")
            trends = con.execute(f"""SELECT e.name, t.window_days, t.trend_direction, t.pct_change
                FROM v_trends t JOIN entities e USING (entity_id)
                WHERE t.metric = ? AND t.trend_direction IN ('alta', 'queda') AND {_NOT_CONSOL}
                {ef}
                ORDER BY t.window_days, ABS(COALESCE(t.pct_change, 0)) DESC LIMIT 4""", [m, *ep]).fetchall()
            for nome, w, d, p in trends:
                if friendly:
                    pc = "" if p is None or pd.isna(p) else f" de {fmt_num(abs(p), 1)}%"
                    lines.append(f"{nome}: {rotulo(m)} em {d}{pc} nos últimos {w} dias.")
                    continue
                lines.append(f"Tendência de {d} em {nome} nos últimos {w} dias"
                             + ("" if p is None or pd.isna(p) else f" ({p:+.1f}%)".replace(".", ",")))
            outs = con.execute(f"""SELECT e.name, o.ref_date, o.value, o.expected, o.score
                FROM v_outliers o JOIN entities e USING (entity_id)
                WHERE o.metric = ? AND o.is_outlier AND {_NOT_CONSOL}
                  AND o.ref_date > ? - INTERVAL 30 DAY{ef}
                ORDER BY ABS(o.score) DESC LIMIT 3""", [m, hoje, *ep]).fetchall()
            if outs:
                for nome, d, v, ex, sc in outs:
                    if friendly:
                        lines.append(f"{nome}: em {pd.Timestamp(d):%d/%m/%Y}, {rotulo(m)} ficou em {fmt_num(v)}, "
                                     f"{'acima' if v > ex else 'abaixo'} do esperado ({fmt_num(ex)}).")
                        continue
                    lines.append(f"Outlier em {nome} no dia {pd.Timestamp(d):%d/%m/%Y}: observado {fmt_num(v)} "
                                 f"vs esperado {fmt_num(ex)} (score {fmt_num(sc, 1)})")
            elif not friendly:
                lines.append(f"Sem outliers de {m} nos últimos 30 dias" + (" nesses ativos." if names else "."))
        return lines
    except Exception:
        return []
    finally:
        con.close()
