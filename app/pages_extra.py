"""Views de Dados (tabelas brutas) e Sobre os dados."""
import pandas as pd
import streamlit as st

from chat_inteligente import overview
from chat_inteligente.ml import outliers as ml_out, trends as ml_tr


def dados(info: dict) -> None:
    if not info["ok"]:
        st.info("Gere os dados primeiro (veja a barra lateral).")
        return
    st.caption("Dados brutos e resultados dos modelos, somente leitura. "
               "Os nomes das colunas são os mesmos que o chat usa nas consultas.")
    ents = overview.entities()
    f1, f2, f3 = st.columns(3)
    tbl = f1.selectbox("Tabela", list(overview.TABLES), key="dt_tbl")
    st.caption(overview.TABLES[tbl])
    cols = overview.table_columns(tbl)
    ent_id = metric = d0 = d1 = None
    only_out = False
    if "entity_id" in cols:
        nm = f2.selectbox("Ativo", ["Todos"] + ents["name"].tolist(), key="dt_ent")
        if nm != "Todos":
            ent_id = ents.loc[ents["name"] == nm, "entity_id"].iloc[0]
    if "metric" in cols:
        mt = f3.selectbox("Métrica", ["Todas"] + overview.metrics(), key="dt_met")
        metric = None if mt == "Todas" else mt
    g1, g2 = st.columns(2)
    if "ref_date" in cols:
        lo, hi = overview.date_bounds()
        rng = g1.date_input("Período", value=(pd.Timestamp(lo).date(), pd.Timestamp(hi).date()),
                            min_value=pd.Timestamp(lo).date(), max_value=pd.Timestamp(hi).date(), key="dt_rng")
        if isinstance(rng, (tuple, list)) and len(rng) == 2:
            d0, d1 = str(rng[0]), str(rng[1])
    if "is_outlier" in cols:
        only_out = g2.checkbox("Somente outliers", key="dt_out")
    df, total = overview.load_table(tbl, ent_id, metric, d0, d1, only_out)
    st.markdown(f"**{total:,}** linhas".replace(",", ".")
                + (f" (mostrando as primeiras {len(df):,})".replace(",", ".") if total > len(df) else ""))
    st.dataframe(df, hide_index=True)
    st.download_button("Baixar CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{tbl}.csv", mime="text/csv", key="dt_dl")


def sobre(info: dict, cat: dict) -> None:
    st.subheader("O que é este projeto")
    st.markdown(
        "Camada de **IA conversacional** sobre resultados de modelos de ML, independente do sistema de origem. "
        "A fonte só precisa preencher `entities`, `metrics_catalog` e `daily_metrics`; o restante do fluxo é o mesmo.")
    src = info.get("source") if info["ok"] else None
    st.markdown(f"**Fonte atual dos dados:** {src or 'não registrada'}")
    st.warning("Os dados são **simulados** para demonstração: uma usina siderúrgica integrada fictícia, com duas plantas, "
               "gerada a partir de 2021-01-01 com tendências, sazonalidade, paradas, falhas e episódios plantados. "
               "Ordens de grandeza e limites foram calibrados por referências públicas do setor, não são dados de nenhuma empresa.")
    st.subheader("Contexto simulado")
    st.markdown("""
- **Produção (diária):** Alto-Forno 1 e 2 (gusa), Laminador de Tiras a Quente (bobinas), Linhas de Galvanização 1 e 2, com taxa de combustível, disponibilidade, rendimento metálico, rejeição, consumo de zinco, etc.
- **Segurança:** desvios, ocorrências, incidentes e acidentes por área, mais horas-homem trabalhadas (para taxa por milhão de HH). A entidade *Segurança — Consolidado* é a soma das áreas.
- **Meio ambiente:** emissões atmosféricas (particulados, NOx), efluente (pH, temperatura, óleos e graxas), intensidades por tonelada de aço (CO₂, SOx, NOx, particulados), energia, água, reaproveitamento de coprodutos e recirculação de água.
""")
    st.subheader("Fluxo")
    st.markdown("""
1. Os dados base são atualizados.
2. O job diário `run_daily` executa os modelos e grava os resultados em tabelas.
3. O chat gera SQL sobre essas tabelas, valida (somente `SELECT`, só tabelas permitidas, com limite de linhas) e executa em modo somente leitura.
4. A resposta cita os valores e traz o contexto dos modelos (tendências e outliers recentes das métricas consultadas).
""")
    st.subheader("Modelos")
    st.markdown(
        f"- **Outliers:** o esperado é a mediana do mesmo dia da semana nas últimas 8 semanas; a escala é a mediana robusta dos "
        f"resíduos recentes. Séries de contagem (acidentes, desvios…) usam cauda de Poisson. Marca outlier quando |score| ≥ {ml_out.THRESHOLD}. "
        f"Guarda todos os sinalizados e os últimos {ml_out.LOOKBACK_DAYS} dias avaliados.\n"
        f"- **Tendência:** regressão linear nas janelas de {', '.join(map(str, ml_tr.WINDOWS))} dias, sem o efeito de dia da semana, "
        f"com p-valor corrigido por autocorrelação e pontos extremos limitados. Só é 'alta' ou 'queda' se p < {ml_tr.ALPHA} e o efeito "
        f"for relevante frente à variabilidade da série (e, para contagens, com eventos suficientes).")
    st.subheader("Referências usadas para calibrar")
    st.markdown("""
- Usiminas, relatório e posicionamentos de sustentabilidade (emissões, água, coprodutos) e notícias de capacidade de alto-forno e galvanização.
- worldsteel, *Sustainability Indicators* 2024 (intensidade de CO₂, energia, água, emissões por tonelada de aço).
- Aço Brasil, anuários e indicadores ambientais do setor.
- CONAMA 430/2011 (pH 5–9, temperatura ≤ 40 °C, óleos e graxas minerais ≤ 20 mg/L no lançamento de efluentes).
- Pirâmide de segurança de Bird (desvio → incidente → acidente) e taxas por milhão de horas-homem.
Metas internas (ex.: CO₂ 2,10 t/t) são **fictícias**. Detalhes em `docs/referencias.md`.
""")
    st.subheader("Tabelas que o chat enxerga")
    for t, d in cat["tables"].items():
        with st.expander(f"{t} — {d['description']}"):
            st.dataframe(pd.DataFrame({"coluna": list(d["columns"]),
                                       "descrição": list(d["columns"].values())}), hide_index=True)
    st.caption("Limites: o chat responde apenas com o que está nessas tabelas; a qualidade do SQL depende do modelo de LLM configurado.")
