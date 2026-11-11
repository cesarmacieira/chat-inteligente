"""Nomes amigáveis e formatação pt-BR para a diretoria (nada de nome de coluna "cru" na tela)."""
import re

import pandas as pd

from .context import fmt_num

METRIC_LABELS = {
    "producao_t": "Produção (t)",
    "taxa_combustivel_kg_t": "Consumo de combustível (kg/t de gusa)",
    "disponibilidade_pct": "Disponibilidade (%)",
    "rendimento_metalico_pct": "Rendimento metálico (%)",
    "consumo_gas_reaquecimento_gj_t": "Consumo de gás no reaquecimento (GJ/t)",
    "taxa_rejeicao_pct": "Taxa de rejeição (%)",
    "consumo_zinco_kg_t": "Consumo de zinco (kg/t)",
    "velocidade_linha_m_min": "Velocidade da linha (m/min)",
    "desvios": "Desvios de segurança",
    "ocorrencias": "Quase-acidentes",
    "incidentes": "Incidentes",
    "acidentes": "Acidentes",
    "horas_homem_trabalhadas": "Horas-homem trabalhadas",
    "emissao_particulados_mg_nm3": "Emissão de particulados (mg/Nm³)",
    "emissao_nox_mg_nm3": "Emissão de NOx (mg/Nm³)",
    "ph_efluente": "pH do efluente",
    "temperatura_efluente_c": "Temperatura do efluente (°C)",
    "oleos_graxas_mg_l": "Óleos e graxas (mg/L)",
    "intensidade_co2_t_t": "Emissão de CO₂ (t por t de aço)",
    "consumo_energia_gj_t": "Consumo de energia (GJ por t de aço)",
    "consumo_agua_m3_t": "Consumo de água (m³ por t de aço)",
    "taxa_reaproveitamento_coprodutos_pct": "Reaproveitamento de coprodutos (%)",
    "taxa_recirculacao_agua_pct": "Recirculação de água (%)",
    "intensidade_particulados_kg_t": "Particulados (kg por t de aço)",
    "intensidade_sox_kg_t": "SOx (kg por t de aço)",
    "intensidade_nox_kg_t": "NOx (kg por t de aço)",
}

COLUMN_LABELS = {
    "name": "Ativo", "nome": "Ativo", "ativo": "Ativo", "entity": "Ativo", "entity_id": "Código do ativo",
    "planta": "Planta", "tipo": "Tipo", "area": "Área", "ref_date": "Data", "data": "Data", "dia": "Dia",
    "metric": "Indicador", "metrica": "Indicador", "indicador": "Indicador", "value": "Valor", "valor": "Valor",
    "unidade": "Unidade", "descricao": "Descrição", "agregacao": "Forma de agregação", "ano": "Ano",
    "mes": "Mês", "trimestre": "Trimestre", "semana": "Semana", "total": "Total", "media": "Média",
    "expected": "Valor esperado", "esperado": "Valor esperado", "desvio": "Desvio", "score": "Intensidade",
    "direction": "Direção", "direcao": "Direção", "tendencia": "Tendência", "variacao_pct": "Variação (%)",
    "window_days": "Janela (dias)", "janela": "Janela (dias)", "slope": "Inclinação", "p_value": "Confiança",
    "is_outlier": "Fora do padrão", "limite_superior": "Limite superior", "limite_inferior": "Limite inferior",
    "qtd": "Quantidade", "quantidade": "Quantidade", "linhas": "Linhas",
}
_SUFFIX = [("_pct", " (%)"), ("_t", " (t)"), ("_kg_t", " (kg/t)"), ("_gj_t", " (GJ/t)")]
_TEXT_MAP = {"alta": "alta", "queda": "queda", "estavel": "estável", "estável": "estável",
             "high": "acima do esperado", "low": "abaixo do esperado", "up": "alta", "down": "queda"}
_ID_COLS = {"ano", "year", "mes", "trimestre", "semana", "janela", "window_days"}


def rotulo(metric: str) -> str:
    return METRIC_LABELS.get(metric) or humanize(metric)


def humanize(col: str) -> str:
    c = str(col)
    if c in METRIC_LABELS:
        return METRIC_LABELS[c]
    if c.lower() in COLUMN_LABELS:
        return COLUMN_LABELS[c.lower()]
    base, suf = c, ""
    for s, lab in _SUFFIX:
        if c.endswith(s):
            base, suf = c[: -len(s)], lab
            break
    txt = base.replace("_", " ").strip()
    return (txt[:1].upper() + txt[1:] + suf) if txt else c


def clean_text(text: str) -> str:
    """Troca ids de métricas (producao_t, taxa_rejeicao_pct...) pelo nome amigável dentro de um texto."""
    for k in sorted(METRIC_LABELS, key=len, reverse=True):
        text = re.sub(rf"`?\b{re.escape(k)}\b`?", METRIC_LABELS[k], text)
    return text


def pretty_df(df: pd.DataFrame) -> pd.DataFrame:
    """Cópia pronta para a diretoria: títulos em português, datas dd/mm/aaaa, números no padrão pt-BR."""
    out = df.copy()
    for c in list(out.columns):
        s = out[c]
        low = str(c).lower()
        if pd.api.types.is_datetime64_any_dtype(s):
            out[c] = s.dt.strftime("%d/%m/%Y")
        elif low in ("metric", "metrica", "indicador") or (s.dtype == object and s.isin(METRIC_LABELS).any()):
            out[c] = s.map(lambda v: METRIC_LABELS.get(v, v))
        elif pd.api.types.is_bool_dtype(s):
            out[c] = s.map({True: "Sim", False: "Não"})
        elif pd.api.types.is_float_dtype(s):
            nd = 1 if (s.dropna().abs() >= 100).all() and len(s.dropna()) else 2
            out[c] = s.map(lambda v, nd=nd: fmt_num(v, nd))
        elif pd.api.types.is_integer_dtype(s):
            out[c] = s.astype(str) if low in _ID_COLS or low.startswith(("ano", "mes")) else s.map(lambda v: fmt_num(v, 0))
        elif s.dtype == object and low in ("tendencia", "direction", "direcao"):
            out[c] = s.map(lambda v: _TEXT_MAP.get(str(v).lower(), v))
    out.columns = _dedupe([humanize(c) for c in out.columns])
    return out


def _dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    res = []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        res.append(n if seen[n] == 1 else f"{n} ({seen[n]})")
    return res
