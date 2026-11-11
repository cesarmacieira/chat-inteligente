"""Sub-abas da aba Análises. Cada função desenha uma sub-aba."""
import numpy as np
import pandas as pd
import streamlit as st

from chat_inteligente import analytics as A
from chat_inteligente.labels import pretty_df, rotulo

_PROD_TIPOS = ["alto_forno", "laminador", "galvanizacao"]
_NIVEIS = {"Planta": "planta", "Ativo": "entity", "Total": "total"}


def _table(df) -> None:
    """Tabela para a diretoria: títulos em português, datas e números no padrão pt-BR."""
    st.dataframe(pretty_df(df), hide_index=True)


def _wide(df: pd.DataFrame) -> pd.DataFrame:
    return df.pivot(index="periodo", columns="grupo", values="valor") if not df.empty else df


def _delta(cur, prev, pct=True):
    if prev is None or np.isnan(prev) or prev == 0 or np.isnan(cur):
        return None
    return f"{(cur / prev - 1) * 100:+.1f}%"


def _fmt(v, nd=0):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def periodo_selector(key: str) -> dict:
    return A.resolve_period(st.selectbox("Período", A.PERIODOS, index=2, key=f"per_{key}"))


# ---------------------------------------------------------------- visão executiva
def executiva(info):
    per = periodo_selector("exec")
    d0, d1, p0, p1 = per["d0"], per["d1"], per["p0"], per["p1"]
    st.caption(f"{d0} a {d1}" + (f" · comparado com {p0} a {p1}" if p0 else " · sem período anterior para comparar"))
    r1 = st.columns(4)
    for col, (nome, tipo) in zip(r1, [("Gusa (t)", "alto_forno"), ("Bobinas a quente (t)", "laminador"),
                                       ("Galvanizados (t)", "galvanizacao")]):
        cur = A.total("producao_t", d0, d1, tipo=tipo)
        prev = A.total("producao_t", p0, p1, tipo=tipo) if p0 else np.nan
        col.metric(nome, _fmt(cur), _delta(cur, prev))
    ac = A.total("acidentes", d0, d1)
    acp = A.total("acidentes", p0, p1) if p0 else np.nan
    r1[3].metric("Acidentes", _fmt(ac), _delta(ac, acp), delta_color="inverse")
    r2 = st.columns(4)
    hh = A.total("horas_homem_trabalhadas", d0, d1)
    r2[0].metric("Acidentes por milhão de HH", _fmt(ac * 1e6 / hh if hh else np.nan, 2))
    r2[1].metric("Incidentes", _fmt(A.total("incidentes", d0, d1)))
    exc = A.excedencias(d0, d1, limit=100000)
    r2[2].metric("Medições fora do limite (ambiental)", _fmt(len(exc)))
    k = A.ml_kpis(d1)
    r2[3].metric("Outliers (90 dias)", _fmt(k["outliers_90d"]))

    st.subheader("Produção por mês")
    s = A.series("producao_t", d0, d1, "month" if per["days"] > 100 else "day", "entity")
    st.line_chart(_wide(s))
    l, r = st.columns(2)
    with l:
        st.subheader("Acidentes por área")
        t = A.seguranca_totais(d0, d1)
        st.bar_chart(t.set_index("area")["acidentes"].rename("Acidentes"))
    with r:
        st.subheader("Itens que merecem atenção")
        tr = A.trends_table(90, directions=["alta", "queda"]).head(8)
        _table(tr[["ativo", "metrica", "tendencia", "variacao_pct"]])


# ---------------------------------------------------------------------- produção
def producao(info):
    per = periodo_selector("prod")
    d0, d1 = per["d0"], per["d1"]
    ents = A.entities_with("producao", _PROD_TIPOS)
    resumo = A.producao_resumo(d0, d1, per["p0"], per["p1"])
    st.subheader("Resumo por equipamento")
    _table(resumo)
    g = _NIVEIS[st.radio("Agrupar produção por", list(_NIVEIS), horizontal=True, key="prod_nivel")]
    grain = A.grain_for(per["days"])
    s = A.series("producao_t", d0, d1, grain, g, entity_ids=ents["entity_id"].tolist())
    st.subheader(f"Produção por {dict(day='dia', week='semana', month='mês')[grain]}")
    st.line_chart(_wide(s))
    l, r = st.columns(2)
    with l:
        st.subheader("Produção anual por equipamento")
        ya = A.series("producao_t", "2021-01-01", d1, "year", "entity", ents["entity_id"].tolist())
        ya["periodo"] = pd.to_datetime(ya["periodo"]).dt.year.astype(str)
        st.bar_chart(ya.pivot(index="periodo", columns="grupo", values="valor"))
        st.caption("O ano corrente é parcial.")
    with r:
        st.subheader("Mesmo mês em anos diferentes")
        nome = st.selectbox("Equipamento", ents["name"].tolist(), key="prod_yoy_ent")
        eid = ents.loc[ents["name"] == nome, "entity_id"].iloc[0]
        st.line_chart(A.yoy(eid, "producao_t"))
    st.subheader("Paradas e produção reduzida")
    nome2 = st.selectbox("Equipamento", ents["name"].tolist(), key="prod_stop_ent")
    eid2 = ents.loc[ents["name"] == nome2, "entity_id"].iloc[0]
    st.caption("Período contínuo com produção abaixo de 25% da mediana histórica do equipamento.")
    p = A.paradas(eid2, "2021-01-01", d1)
    _table(p if not p.empty else pd.DataFrame({"info": ["Sem paradas no histórico."]}))
    st.subheader("Eficiência e qualidade")
    mets = A.available_metrics("producao", eid2)
    mets = mets[mets["metric"] != "producao_t"]
    if not mets.empty:
        m = st.selectbox("Indicador", mets["metric"].tolist(), key="prod_kpi",
                         format_func=rotulo)
        sm = A.series(m, d0, d1, grain, "entity", [eid2])
        st.line_chart(_wide(sm))
        st.caption(A.metric_info(m)["descricao"])
        other = [x for x in mets["metric"] if x != m]
        if other:
            m2 = st.selectbox("Relacionar com", other, key="prod_kpi2", format_func=rotulo)
            pr = A.pair(eid2, m, m2, d0, d1)
            if len(pr) > 5:
                st.scatter_chart(pr.rename(columns=rotulo), x=rotulo(m), y=rotulo(m2))
                st.caption(f"Correlação de Pearson no período: {pr[m].corr(pr[m2]):.2f} (associação, não causa).")


# ---------------------------------------------------------------------- segurança
def seguranca(info):
    per = periodo_selector("seg")
    d0, d1 = per["d0"], per["d1"]
    st.caption("Desvio → ocorrência → incidente → acidente: pirâmide de segurança, do evento mais frequente (desvio, "
               "condição ou ato inseguro) ao mais grave. Taxa = acidentes por milhão de horas-homem (HH).")
    t = A.seguranca_totais(d0, d1)
    tot = t[["desvios", "ocorrencias", "incidentes", "acidentes"]].sum()
    hh = t["horas_homem_trabalhadas"].sum()
    c = st.columns(5)
    for col, n in zip(c, ["desvios", "ocorrencias", "incidentes", "acidentes"]):
        col.metric(n.capitalize(), _fmt(tot[n]))
    c[4].metric("Acidentes / milhão HH", _fmt(tot["acidentes"] * 1e6 / hh if hh else np.nan, 2))
    l, r = st.columns(2)
    with l:
        st.subheader("Pirâmide no período")
        st.bar_chart(tot.rename("quantidade"))
    with r:
        st.subheader("Por área")
        _table(t.round(2))
    st.subheader("Evolução")
    m = st.selectbox("Indicador", A.SEG_METRICS, index=3, key="seg_m", format_func=rotulo)
    grain = "month" if per["days"] > 100 else "week"
    ser = A.series(m, d0, d1, grain, "entity")
    st.bar_chart(_wide(ser[~ser["grupo"].str.contains("Consolidado")]))
    l, r = st.columns(2)
    with l:
        st.subheader("Taxa anual de acidentes por milhão de HH")
        ta = A.seguranca_anual_taxa()
        ta = ta[~ta["area"].str.contains("Consolidado")]
        st.line_chart(ta.pivot(index="ano", columns="area", values="taxa"))
    with r:
        st.subheader("Dias sem acidente")
        _table(A.dias_sem_acidente())
    l, r = st.columns(2)
    with l:
        st.subheader("Dia da semana (média diária)")
        mm = st.selectbox("Indicador ", A.SEG_METRICS, key="seg_dow", format_func=rotulo)
        ps = A.padrao_semanal(mm, d0, d1)
        st.bar_chart(ps.set_index("dia")["media"])
    with r:
        st.subheader("Acidentes recentes")
        _table(A.acidentes_recentes(d0, d1))


# ------------------------------------------------------------------ meio ambiente
def ambiente(info):
    per = periodo_selector("amb")
    d0, d1 = per["d0"], per["d1"]
    st.caption("Limites: pH, óleos e graxas, temperatura do efluente seguem a CONAMA 430/2011; os demais são "
               "metas internas fictícias calibradas por referências do setor (veja a aba Sobre).")
    conf = A.conformidade(d0, d1)
    exc = A.excedencias(d0, d1, limit=100000)
    c = st.columns(3)
    c[0].metric("Medições com limite", _fmt(conf["medicoes"].sum()))
    c[1].metric("Fora do limite", _fmt(conf["fora_do_limite"].sum()))
    c[2].metric("% fora", _fmt(100 * conf["fora_do_limite"].sum() / max(conf["medicoes"].sum(), 1), 2))
    st.subheader("Conformidade por ponto e indicador")
    _table(conf)
    st.subheader("Indicador ao longo do tempo")
    mets = A.available_metrics("meio_ambiente")
    m = st.selectbox("Indicador", mets["metric"].tolist(), key="amb_m",
                     format_func=rotulo)
    info_m = A.metric_info(m)
    grain = A.grain_for(per["days"])
    s = _wide(A.series(m, d0, d1, grain, "entity"))
    for lim, nm in [(info_m["limite_superior"], "limite superior"), (info_m["limite_inferior"], "limite inferior")]:
        if lim is not None and not pd.isna(lim):
            s[nm] = lim
    st.line_chart(s)
    st.caption(info_m["descricao"] + (f" Referência: {info_m['referencia']}" if info_m.get("referencia") else ""))
    l, r = st.columns(2)
    with l:
        st.subheader("Sazonalidade (média por mês)")
        pts = A.entities_with("meio_ambiente")
        pts = pts[pts["entity_id"].isin(A._df("SELECT DISTINCT entity_id FROM daily_metrics WHERE metric=?", [m])["entity_id"])]
        nome = st.selectbox("Ponto", pts["name"].tolist(), key="amb_pt")
        eid = pts.loc[pts["name"] == nome, "entity_id"].iloc[0]
        st.bar_chart(A.sazonalidade(eid, m).set_index("mes")["media"])
    with r:
        st.subheader("Comparação com média mundial (worldsteel 2024)")
        if m in A.REF_WORLDSTEEL:
            un, ref, src = A.REF_WORLDSTEEL[m]
            v = A.total(m, d0, d1)
            st.metric(f"{m} ({un})", _fmt(v, 2), f"{(v / ref - 1) * 100:+.1f}% vs referência {ref}")
            st.caption(src + ". Dados da usina são fictícios.")
        else:
            st.info("Este indicador não tem referência mundial cadastrada.")
    st.subheader("Excedências no período")
    _table(exc.head(200) if not exc.empty else pd.DataFrame({"info": ["Nenhuma excedência."]}))


# ------------------------------------------------------------------------- ML
def modelos(info):
    d1 = info["date_max"]
    k = A.ml_kpis(d1)
    c = st.columns(5)
    c[0].metric("Outliers (7 dias)", k["outliers_7d"])
    c[1].metric("Outliers (90 dias)", k["outliers_90d"])
    c[2].metric("Outliers (histórico)", k["outliers_total"])
    c[3].metric("Tendências de alta (90d)", k["alta_90"])
    c[4].metric("Tendências de queda (90d)", k["queda_90"])
    f1, f2 = st.columns(2)
    area_lbl = f1.selectbox("Área", ["Todas"] + list(A.AREAS.values()), key="ml_area")
    area = None if area_lbl == "Todas" else {v: k_ for k_, v in A.AREAS.items()}[area_lbl]
    per = f2.selectbox("Período dos outliers", A.PERIODOS, index=1, key="ml_per")
    p = A.resolve_period(per)
    st.subheader("Outliers por mês")
    om = A.outliers_por_mes(area)
    if not om.empty:
        st.bar_chart(om.pivot(index="mes", columns="area", values="outliers").fillna(0))
    l, r = st.columns(2)
    with l:
        st.subheader("Ativos com mais outliers")
        oe = A.outliers_por_entidade(p["d0"], p["d1"])
        if not oe.empty:
            st.bar_chart(oe.set_index("ativo")["outliers"])
    with r:
        st.subheader("Lista")
        _table(A.outliers_table(p["d0"], p["d1"], area))
    st.subheader("Tendências")
    t1, t2 = st.columns(2)
    win = t1.selectbox("Janela (dias)", [30, 90, 365], index=1, key="ml_win")
    dirs = t2.multiselect("Direção", ["alta", "queda", "estavel"], default=["alta", "queda"], key="ml_dir")
    tt = A.trends_table(win, area, directions=dirs or None)
    a, b = st.columns([1, 2])
    with a:
        mx = A.trends_matrix()
        mx = mx[mx["janela"] == win]
        if area:
            mx = mx[mx["area"] == area]
        if not mx.empty:
            st.bar_chart(mx.groupby("tendencia")["series"].sum())
    with b:
        _table(tt)
    st.caption("Tendência 'alta' ou 'queda' só aparece quando é estatisticamente significativa e de tamanho relevante "
               "em relação à variabilidade da série; o resto é 'estável'.")


# ------------------------------------------------------------------------ detalhe
def detalhe(info):
    ents = A._df("SELECT entity_id, name FROM entities ORDER BY name")
    mets_all = A._df("SELECT metric, area FROM metrics_catalog ORDER BY area, metric")
    c1, c2, c3 = st.columns(3)
    nome = c1.selectbox("Ativo", ents["name"].tolist(), key="det_ent")
    eid = ents.loc[ents["name"] == nome, "entity_id"].iloc[0]
    ok = A._df("SELECT DISTINCT metric FROM daily_metrics WHERE entity_id=?", [eid])["metric"].tolist()
    m = c2.selectbox("Indicador", ok, key="det_met", format_func=rotulo)
    per = c3.selectbox("Período", A.PERIODOS, index=2, key="det_per")
    p = A.resolve_period(per)
    d = A.daily(eid, m, p["d0"], p["d1"]).set_index("ref_date")["value"].rename("Observado")
    ex = A.expected_series(eid, m, p["d0"], p["d1"]).set_index("ref_date")["expected"].rename("Esperado")
    st.line_chart(pd.concat([d, ex], axis=1))
    mi = A.metric_info(m)
    st.caption(f"{mi['descricao']} · unidade: {mi['unidade']} · agregação: {mi['agregacao']}. "
               "A linha 'esperado' é a base do modelo de outlier (mediana do mesmo dia da semana).")
    l, r = st.columns(2)
    with l:
        st.subheader("Outliers")
        so = A.series_outliers(eid, m, p["d0"], p["d1"])
        _table(so if not so.empty else pd.DataFrame({"info": ["Nenhum outlier no período."]}))
    with r:
        st.subheader("Tendências")
        _table(A.series_trends(eid, m))
    if len(d):
        st.subheader("Estatísticas")
        _table(d.describe().round(3).to_frame().T)
