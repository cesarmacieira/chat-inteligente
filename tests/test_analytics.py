import numpy as np
from chat_inteligente import analytics as A


def test_period_resolution():
    p = A.resolve_period("Últimos 30 dias")
    assert p["days"] == 30 and p["d1"] == "2026-11-09" and p["p0"] and p["p1"] < p["d0"]
    assert A.resolve_period("Todo o período")["p0"] is None
    assert A.resolve_period("Ano atual")["d0"] == "2026-01-01"
    assert A.grain_for(30) == "day" and A.grain_for(365) == "week" or A.grain_for(365) == "week"
    assert A.grain_for(1800) == "month"


def test_aggregation_follows_catalog():
    p = A.resolve_period("Últimos 12 meses")
    soma = A.total("producao_t", p["d0"], p["d1"], tipo="alto_forno")
    assert soma > 1e6                                  # soma de toneladas
    rend = A.total("rendimento_metalico_pct", p["d0"], p["d1"], tipo="laminador")
    assert 80 < rend < 100                             # média de %, não soma


def test_total_excludes_consolidated():
    p = A.resolve_period("Todo o período")
    por_area = A.seguranca_totais(p["d0"], p["d1"])["acidentes"].sum()
    assert por_area == A.total("acidentes", p["d0"], p["d1"])


def test_producao_and_paradas():
    p = A.resolve_period("Últimos 12 meses")
    r = A.producao_resumo(p["d0"], p["d1"], p["p0"], p["p1"])
    assert len(r) == 5 and (r["total_t"] > 0).all() and "variacao_pct" in r
    par = A.paradas("AF02", "2021-01-01", "2026-11-09")
    assert par["dias"].max() > 150                      # parada longa de 2024 plantada


def test_safety_tables():
    d = A.dias_sem_acidente()
    assert (d["dias_sem_acidente"] >= 0).all() and len(d) == 10
    t = A.seguranca_anual_taxa()
    assert t["taxa"].dropna().ge(0).all()
    assert len(A.padrao_semanal("acidentes", "2021-01-01", "2026-11-09")) == 7


def test_environment():
    p = A.resolve_period("Todo o período")
    c = A.conformidade(p["d0"], p["d1"])
    assert (c["pct_fora"].between(0, 100)).all() and c["fora_do_limite"].sum() > 0
    e = A.excedencias(p["d0"], p["d1"], 1000)
    assert not e.empty


def test_ml_helpers():
    k = A.ml_kpis("2026-11-09")
    assert k["outliers_total"] >= k["outliers_90d"] >= k["outliers_7d"] >= 0
    assert not A.outliers_por_mes().empty
    assert not A.trends_matrix().empty
    assert not A.trends_table(365, directions=["alta", "queda"]).empty
    ex = A.expected_series("AF01", "producao_t", "2026-01-01", "2026-11-09")
    assert len(ex) > 0 and np.isfinite(ex["expected"]).all()
