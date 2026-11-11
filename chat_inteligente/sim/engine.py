"""Gerador de dados fictícios: produção, segurança e meio ambiente de uma siderúrgica integrada.

Cada série = base × tendência × sazonalidade × ruído autocorrelacionado + eventos
(paradas, reforma de alto-forno, falhas de filtro, aglomerados de acidentes...).
Eventos de 2026 são "histórias" propositais para a demo (anomalias e tendências recentes).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import lfilter

from .profiles import ENTITIES, METRICS


class Ctx:
    def __init__(self, start, end, seed):
        self.dates = pd.date_range(start, end, freq="D")
        self.n = len(self.dates)
        self.rng = np.random.default_rng(seed)
        self.yrs = np.arange(self.n) / 365.25
        self.dow = self.dates.dayofweek.to_numpy()
        self.doy = self.dates.dayofyear.to_numpy()
        self.year = self.dates.year.to_numpy()
        self.out: dict[tuple[str, str], np.ndarray] = {}
        self.offline: dict[str, np.ndarray] = {}
        self.dry = 0.5 * (1 + np.cos(2 * np.pi * (self.doy - 200) / 365.25))      # pico em julho
        self.summer = 0.5 * (1 + np.cos(2 * np.pi * (self.doy - 30) / 365.25))    # pico em janeiro

    # --- utilitários
    def ar1(self, sd, phi=0.6):
        e = self.rng.normal(0, sd * np.sqrt(1 - phi ** 2), self.n)
        return lfilter([1.0], [1.0, -phi], e)

    def between(self, a, b):
        return np.asarray((self.dates >= pd.Timestamp(a)) & (self.dates <= pd.Timestamp(b)))

    def days_since(self, a):
        return np.maximum(0, (self.dates - pd.Timestamp(a)).days.to_numpy()).astype(float)

    def ramp(self, a, b, v0, v1):
        ta, tb = pd.Timestamp(a), pd.Timestamp(b)
        frac = np.clip((self.dates - ta).days.to_numpy() / max((tb - ta).days, 1), 0, 1)
        return v0 + (v1 - v0) * frac

    def restart(self, end, days=14, v0=0.6):
        te = pd.Timestamp(end)
        frac = np.clip((self.dates - te).days.to_numpy() / days, 0, 1)
        return np.where(self.dates <= te, 1.0, v0 + (1 - v0) * frac)

    def stops(self, per_year, dmin, dmax, fmax):
        f = np.ones(self.n)
        for s in self.rng.integers(0, self.n, self.rng.poisson(per_year * self.n / 365.25)):
            d = int(self.rng.integers(dmin, dmax + 1))
            f[s:s + d] = np.minimum(f[s:s + d], self.rng.uniform(0, fmax))
        return f

    def put(self, eid, metric, arr):
        self.out[(eid, metric)] = np.asarray(arr, dtype=float)


# ------------------------------------------------------------------ produção
def gen_af(c, eid, base, fuel0, reline=None, idle=None, aging=0.0, stops_py=4.0):
    cap = base * (1 + 0.008 * c.yrs) * (1 - aging * c.yrs)
    off = np.zeros(c.n, bool)
    restart = np.ones(c.n)
    if reline:
        a, b = reline
        degrade = np.where(c.dates <= pd.Timestamp(b),
                           c.ramp(pd.Timestamp(a) - pd.Timedelta(days=365), a, 1.0, 0.97), 1.0)
        cap = cap * degrade * np.where(c.dates > pd.Timestamp(b), 1.05, 1.0)
        off |= c.between(a, b)
        restart *= c.restart(b, 14, 0.6)
    if idle:
        off |= c.between(*idle)
        restart *= c.restart(idle[1], 10, 0.5)
    up = c.stops(stops_py, 1, 3, 0.5) * restart
    prod = np.maximum(cap * up * (1 + c.ar1(0.02, 0.6)), 0)
    prod = np.where(off, 0.0, prod)
    util = np.minimum(prod / cap, 1.0)
    fuel = fuel0 * (1 - 0.006 * c.yrs) * (1 + 0.12 * (1 - util)) * (1 + c.ar1(0.012, 0.5))
    if reline:
        fuel = fuel * np.where(c.dates > pd.Timestamp(reline[1]), 0.98, 1.0)
    disp = np.minimum(100, 99.2 + c.ar1(0.5, 0.3)) * np.clip(up, 0, 1)
    c.put(eid, "producao_t", np.round(prod))
    c.put(eid, "taxa_combustivel_kg_t", np.where(prod <= 0, np.nan, np.round(fuel, 1)))
    c.put(eid, "disponibilidade_pct", np.where(off, 0.0, np.round(disp, 1)))
    c.offline[eid] = prod <= 0


def gen_ltq(c, eid, base):
    market = pd.Series(c.year).map({2021: .97, 2022: 1.0, 2023: .93, 2024: .98,
                                    2025: .92, 2026: .95}).fillna(.95).to_numpy()
    season = 1 + 0.035 * np.sin(2 * np.pi * (c.doy - 60) / 365.25)
    weekly = np.where(c.dow == 6, 0.94, 1.0)
    annual = np.ones(c.n)
    for y in range(c.year.min(), c.year.max() + 1):
        annual = np.where(c.between(f"{y}-07-12", f"{y}-07-18"), 0.15, annual)
    annual = np.where(c.between("2022-10-12", "2022-10-14"), 0.30, annual)
    cap = base * market * season
    up = c.stops(5, 1, 2, 0.6) * annual
    prod = np.maximum(cap * weekly * up * (1 + c.ar1(0.03, 0.5)), 0)
    util = np.minimum(prod / cap, 1.0)
    rend = (96.3 + 0.12 * c.yrs + c.ar1(0.25, 0.5) - 0.8 * (1 - np.minimum(up, 1))
            - 0.004 * c.days_since("2026-04-15"))                  # história: queda de rendimento
    gas = (1.28 * (1 - 0.005 * c.yrs) * (1 + 0.35 * (1 - util)) * (1 + c.ar1(0.025, 0.6))
           * np.where(c.dates >= pd.Timestamp("2025-09-01"), 1.06, 1.0))  # história: degrau de consumo
    ok = prod >= 0.2 * base
    c.put(eid, "producao_t", np.round(prod))
    c.put(eid, "rendimento_metalico_pct", np.where(ok, np.round(np.clip(rend, 90, 99.5), 2), np.nan))
    c.put(eid, "consumo_gas_reaquecimento_gj_t", np.where(ok, np.round(gas, 3), np.nan))
    c.offline[eid] = prod <= 0.05 * base


def gen_galv(c, eid, base, stop_window, rej_story=None, zinc_story=None):
    market = pd.Series(c.year).map({2021: .90, 2022: .98, 2023: 1.0, 2024: 1.03,
                                    2025: 1.0, 2026: .98}).fillna(.98).to_numpy()
    chip = np.where(c.between("2021-04-01", "2021-09-30"), 0.82, 1.0)
    annual = np.ones(c.n)
    for y in range(c.year.min(), c.year.max() + 1):
        annual = np.where(c.between(f"{y}-{stop_window[0]}", f"{y}-{stop_window[1]}"), 0.1, annual)
    up = c.stops(6, 1, 2, 0.5) * annual
    speed = 118 * market * chip * (1 + 0.004 * c.yrs) * (1 + c.ar1(0.03, 0.5)) * up
    prod = np.maximum(base * (speed / 118) * (1 + c.rng.normal(0, 0.02, c.n)), 0)
    rej = c.rng.gamma(6, 3.0 * (1 - 0.04 * c.yrs) / 6)
    if rej_story:
        rej = rej + 0.006 * c.days_since(rej_story)
    zinc = 46 - 0.3 * c.yrs + c.ar1(1.4, 0.5)
    if zinc_story:
        zinc = zinc + 0.025 * c.days_since(zinc_story)
    ok = up >= 0.2
    c.put(eid, "producao_t", np.round(prod))
    c.put(eid, "velocidade_linha_m_min", np.where(ok, np.round(speed, 1), np.nan))
    c.put(eid, "taxa_rejeicao_pct", np.where(ok, np.round(np.clip(rej, 0.2, 20), 2), np.nan))
    c.put(eid, "consumo_zinco_kg_t", np.where(ok, np.round(zinc, 2), np.nan))
    c.offline[eid] = prod <= 0.05 * base


# ------------------------------------------------------------------ segurança
def gen_safety(c, eid, size, headcount, extra=None):
    extra = extra or {}
    wd = lambda mon_fri, sat, sun: np.select([c.dow < 5, c.dow == 5], [mon_fri, sat], sun)
    culture = c.ramp("2021-01-01", "2024-01-01", 0.8, 1.25)       # cultura de reporte cresce
    lam = {
        "desvios": 5.0 * size * culture * wd(1.08, 0.70, 0.55),
        "ocorrencias": 0.33 * size * c.ramp("2021-01-01", "2026-11-01", 1.0, 0.85) * wd(1.03, 0.9, 0.85),
        "incidentes": 0.025 * size * c.ramp("2021-01-01", "2026-11-01", 1.0, 0.80),
        "acidentes": 0.006 * size * c.ramp("2021-01-01", "2026-11-01", 1.25, 0.75),
    }
    hh = headcount * 6.4 * wd(1.0, 0.8, 0.75) * (1 + c.rng.normal(0, 0.03, c.n))
    for fn in extra.get("lam", []):
        fn(c, lam)
    for fn in extra.get("hh", []):
        hh = fn(c, hh)
    for m, l in lam.items():
        mix = c.rng.gamma(25, 1 / 25, c.n) if m in ("desvios", "ocorrencias") else 1.0
        counts = c.rng.poisson(np.maximum(l * mix, 0)).astype(float)
        for fn in extra.get("add", {}).get(m, []):
            counts = fn(c, counts)
        c.put(eid, m, counts)
    c.put(eid, "horas_homem_trabalhadas", np.round(hh))


def _mult(metric, a, b, k):
    def f(c, lam):
        lam[metric] = lam[metric] * np.where(c.between(a, b), k, 1.0)
    return f


def _add_on(date, k):
    def f(c, counts):
        counts = counts.copy()
        counts[c.between(date, date)] += k
        return counts
    return f


def _hh_mult(a, b, k):
    return lambda c, hh: hh * np.where(c.between(a, b), k, 1.0)


# ------------------------------------------------------------------ meio ambiente
def gen_stack(c, eid, pm0, nox0, af=None, pm_events=(), pm_drift=None, nox_step=None):
    dry = c.dry
    pm = pm0 * np.exp(c.ar1(0.18, 0.5)) * (1 + 0.10 * dry)
    nox = nox0 * np.exp(c.ar1(0.08, 0.5))
    for (a, b, mean) in pm_events:
        m = c.between(a, b)
        pm = np.where(m, mean + c.rng.normal(0, 7, c.n), pm)
    if pm_drift:
        pm = pm + 0.06 * c.days_since(pm_drift)
    if nox_step:
        nox = nox * np.where(c.dates > pd.Timestamp(nox_step), 0.95, 1.0)
    off = c.offline.get(af, np.zeros(c.n, bool)) if af else np.zeros(c.n, bool)
    c.put(eid, "emissao_particulados_mg_nm3", np.where(off, np.nan, np.round(pm, 1)))
    c.put(eid, "emissao_nox_mg_nm3", np.where(off, np.nan, np.round(nox, 0)))


def gen_ete(c, eid, ph0, oil0, ph_events=(), oil_events=(), temp_events=(), oil_drift=None):
    ph = ph0 + c.ar1(0.22, 0.5)
    for (a, b, v) in ph_events:
        ph = np.where(c.between(a, b), v + c.rng.normal(0, 0.15, c.n), ph)
    temp = 29 + 3 * c.summer + c.ar1(1.2, 0.7)
    for (a, b, add) in temp_events:
        temp = temp + np.where(c.between(a, b), add, 0.0)
    oil = oil0 * np.exp(c.ar1(0.35, 0.4))
    for (a, b, v) in oil_events:
        oil = np.where(c.between(a, b), v + c.rng.normal(0, 2.5, c.n), oil)
    if oil_drift:
        oil = oil + 0.03 * c.days_since(oil_drift)
    c.put(eid, "ph_efluente", np.round(ph, 2))
    c.put(eid, "temperatura_efluente_c", np.round(temp, 1))
    c.put(eid, "oleos_graxas_mg_l", np.round(np.maximum(oil, 0.2), 1))


def gen_amb(c, eid, co2, energia, agua, reap, recirc, particulados=None, sox=None, nox=None,
            reap_dip=None, recirc_dip=None):
    y = c.yrs
    c.put(eid, "intensidade_co2_t_t", np.round(c.ramp("2021-01-01", "2026-11-09", co2[0], co2[1])
                                                * np.exp(c.ar1(0.015, 0.7)), 3))
    c.put(eid, "consumo_energia_gj_t", np.round(energia * (1 - 0.003 * y) * np.exp(c.ar1(0.015, 0.7)), 2))
    c.put(eid, "consumo_agua_m3_t", np.round(agua * (1 - 0.012 * y) * (1 + 0.08 * c.dry)
                                              * np.exp(c.ar1(0.03, 0.6)), 3))
    r = np.minimum(99.5, reap + 0.25 * y + c.ar1(0.6, 0.5))
    if reap_dip:
        r = r - np.where(c.between(*reap_dip), 6.0, 0.0)
    c.put(eid, "taxa_reaproveitamento_coprodutos_pct", np.round(r, 2))
    w = recirc + c.ar1(0.25, 0.5) - 0.8 * c.dry
    if recirc_dip:
        w = w - np.where(c.between(*recirc_dip), 3.5, 0.0)
    c.put(eid, "taxa_recirculacao_agua_pct", np.round(np.minimum(w, 99.5), 2))
    for name, v in (("intensidade_particulados_kg_t", particulados), ("intensidade_sox_kg_t", sox),
                    ("intensidade_nox_kg_t", nox)):
        if v is not None:
            c.put(eid, name, np.round(v * np.exp(c.ar1(0.12, 0.5)) * (1 + 0.08 * c.dry), 3))


# ------------------------------------------------------------------ orquestração
def build(start="2021-01-01", end=None, seed=2021):
    end = pd.Timestamp(end) if end is not None else pd.Timestamp.today().normalize()
    c = Ctx(start, end, seed)

    gen_af(c, "AF01", base=6800, fuel0=505, reline=("2023-05-15", "2023-10-09"), aging=0.0)
    gen_af(c, "AF02", base=1700, fuel0=530, idle=("2024-06-01", "2024-12-31"), aging=0.01, stops_py=6)
    gen_ltq(c, "LTQ01", base=6400)
    gen_galv(c, "GALV01", base=1230, stop_window=("12-20", "12-24"))
    gen_galv(c, "GALV02", base=950, stop_window=("01-08", "01-12"),
             rej_story="2026-03-01", zinc_story="2026-06-10")

    gen_safety(c, "AF01", 1.6, 520, {"lam": [_mult("desvios", "2023-05-15", "2023-10-09", 1.4),
                                              _mult("ocorrencias", "2023-05-15", "2023-10-09", 1.5)],
                                     "hh": [_hh_mult("2023-05-15", "2023-10-09", 1.6)]})
    gen_safety(c, "AF02", 0.9, 280)
    gen_safety(c, "ACI01", 1.8, 610, {"add": {"incidentes": [_add_on("2026-10-14", 7)],
                                              "acidentes": [_add_on("2023-02-08", 3)]}})
    gen_safety(c, "LTQ01", 1.7, 700)
    gen_safety(c, "UTL01", 0.7, 240)
    gen_safety(c, "MAN01", 2.0, 900, {"lam": [lambda c_, lam: lam.__setitem__(
        "desvios", lam["desvios"] * c_.ramp("2026-05-01", "2026-11-09", 1.0, 0.45))]})
    gen_safety(c, "LOG01", 1.5, 480, {"lam": [_mult("acidentes", "2026-08-01", "2026-10-31", 4.0),
                                               _mult("incidentes", "2026-08-01", "2026-10-31", 2.0)]})
    gen_safety(c, "GALV01", 0.9, 310)
    gen_safety(c, "GALV02", 0.8, 260)
    gen_safety(c, "MAN02", 1.1, 380)

    safety_ids = sorted({e for (e, m) in c.out if m == "acidentes"})
    for m in ("desvios", "ocorrencias", "incidentes", "acidentes", "horas_homem_trabalhadas"):
        c.put("SEG00", m, sum(c.out[(e, m)] for e in safety_ids))

    gen_stack(c, "AF01", 17, 180, af="AF01", pm_events=[("2024-03-04", "2024-03-13", 68)],
              nox_step="2023-10-09")
    gen_stack(c, "AF02", 21, 200, af="AF02", pm_drift="2026-07-01")
    gen_stack(c, "ACI01", 14, 130, pm_events=[("2022-11-20", "2022-11-22", 56)])
    gen_ete(c, "ETE01", 7.5, 4.5, ph_events=[("2025-01-14", "2025-01-16", 9.6)],
            oil_events=[("2025-01-15", "2025-01-17", 26)], temp_events=[("2024-02-12", "2024-02-16", 9.0)])
    gen_ete(c, "ETE02", 7.3, 3.5, ph_events=[("2026-02-09", "2026-02-11", 4.6)], oil_drift="2026-08-01")
    gen_amb(c, "AMB01", (2.20, 2.06), 24.0, 6.3, 94.0, 97.0, particulados=0.30, sox=0.70, nox=0.62,
            reap_dip=("2024-09-10", "2024-10-05"), recirc_dip=("2025-03-12", "2025-03-20"))
    gen_amb(c, "AMB02", (0.32, 0.28), 3.2, 1.25, 91.5, 96.0)

    rows = []
    for (eid, metric), v in c.out.items():
        m = ~np.isnan(v)
        rows.append(pd.DataFrame({"entity_id": eid, "metric": metric,
                                  "ref_date": c.dates[m], "value": v[m]}))
    metrics = pd.concat(rows, ignore_index=True)
    ents = pd.DataFrame(ENTITIES, columns=["entity_id", "name", "planta", "tipo"])
    cat = pd.DataFrame(METRICS, columns=["metric", "area", "unidade", "descricao", "tipo_dado",
                                          "agregacao", "limite_superior", "limite_inferior", "referencia"])
    return ents, cat, metrics
