"""Conferência de números: todo número citado no texto da resposta precisa existir no resultado (ou ser derivável
dele: diferença, variação percentual, participação, soma ou média) ou nas linhas de contexto. O que sobrar é
sinalizado ao usuário para conferir na tabela. É uma checagem de consistência, não uma garantia de correção."""
import re

import numpy as np
import pandas as pd

_NUM = re.compile(r"(?<![\w/,.])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(?![\w/]|[,.]\d)")
_MAX_VALUES = 150
_MONTHS = "janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
# Janelas/posições são reconhecidas pelo contexto anterior; unidades de tempo depois do número podem ser
# medidas reais ("77 dias de parada") e, portanto, não devem ser ignoradas isoladamente.
_AFTER = re.compile(rf"\s*(?:pontos?|marcadores?|itens?|bullets?|linhas?|colunas?|passos?|etapas?|"
                    rf"de\s+(?:{_MONTHS})|/\d{{1,2}}\b)", re.IGNORECASE)
_BEFORE = re.compile(r"(?:top|semana|dia|mês|mes|[uú]ltimos?|pr[oó]ximos?|previs[aã]o\s+de)\s*$", re.IGNORECASE)
_SCALE = re.compile(r"\s*(mil|milh[aã]o|milh[oõ]es|bilh[aã]o|bilh[oõ]es)\b", re.IGNORECASE)
_FACTOR = {"mil": 1e3, "milh": 1e6, "bilh": 1e9}


def _is_descriptive(text: str, m: "re.Match") -> bool:
    if _SCALE.match(text, m.end()):
        return False
    return bool(_AFTER.match(text, m.end()) or _BEFORE.search(text[max(0, m.start() - 20):m.start()]))


def _scaled(text: str, m: "re.Match", v: float, dec: int = 0) -> tuple[float, int]:
    """Aplica "mil/milhão/bilhão": o valor sobe na escala e a casa decimal citada vira tolerância maior."""
    sc = _SCALE.match(text, m.end())
    if not sc:
        return v, dec
    w = sc.group(1).lower()
    f = _FACTOR["mil"] if w == "mil" else _FACTOR["milh"] if w.startswith("milh") else _FACTOR["bilh"]
    return v * f, dec - int(round(np.log10(f)))


def _parse(tok: str) -> tuple[float, int]:
    dec = len(tok.split(",")[1]) if "," in tok else 0
    return float(tok.replace(".", "").replace(",", ".")), dec


def _values(df: pd.DataFrame | None) -> np.ndarray:
    if df is None or df.empty:
        return np.array([])
    num = df.head(30).select_dtypes("number")
    vals = pd.to_numeric(num.stack(), errors="coerce").dropna().to_numpy(dtype=float)
    extra = [float(len(df))] + [float(df[c].sum()) for c in num.columns] + [float(df[c].mean()) for c in num.columns]
    return np.concatenate([vals[:_MAX_VALUES], extra])


def _candidates(v: np.ndarray) -> np.ndarray:
    if len(v) == 0:
        return v
    d = v[:, None] - v[None, :]
    denom = np.where(np.abs(v[None, :]) > 1e-12, np.abs(v[None, :]), np.nan)
    pct, share = d / denom * 100, v[:, None] / denom * 100
    c = np.concatenate([v, np.abs(d).ravel(), np.abs(pct).ravel(), np.abs(share).ravel()])
    return c[np.isfinite(c)]


def _matches(pool: np.ndarray, value: float, decimals: int) -> bool:
    if not len(pool):
        return False
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    if (np.abs(pool - value) <= tol).any():
        return True
    return decimals == 0 and (np.abs(pool - value) <= np.maximum(tol, 0.006 * np.abs(pool))).any()


def derived_pool(row: np.ndarray) -> np.ndarray:
    """Valores deriváveis só da própria linha (diferenças e variações percentuais entre suas colunas)."""
    if len(row) < 2:
        return row
    d = row[:, None] - row[None, :]
    den = np.where(np.abs(row[None, :]) > 1e-12, np.abs(row[None, :]), np.nan)
    c = np.concatenate([np.abs(d).ravel(), np.abs(d / den * 100).ravel(), np.abs(row[:, None] / den * 100).ravel()])
    return c[np.isfinite(c)]


def _entity_mismatches(text: str, df: pd.DataFrame | None) -> set[tuple[int, int]]:
    """Confere o primeiro número após cada dimensão textual contra os valores da mesma linha."""
    if df is None or df.empty:
        return set()
    text_cols = list(df.select_dtypes(include=["object", "string"]).columns)
    num_cols = list(df.select_dtypes("number").columns)
    if not text_cols or not num_cols:
        return set()
    occurrences = []
    for idx, row in df.head(30).iterrows():
        labels = {str(row[c]).strip() for c in text_cols if pd.notna(row[c]) and len(str(row[c]).strip()) >= 2}
        for label in sorted(labels, key=len, reverse=True):
            for match in re.finditer(re.escape(label), text, re.IGNORECASE):
                occurrences.append((match.start(), match.end(), idx))
    occurrences.sort()
    bad: set[tuple[int, int]] = set()
    for pos, (_, end, idx) in enumerate(occurrences):
        stop = occurrences[pos + 1][0] if pos + 1 < len(occurrences) else len(text)
        number = next(_NUM.finditer(text, end, stop), None)
        if not number:
            continue
        value, dec = _parse(number.group(1))
        if 1990 <= value <= 2100:
            continue
        row_pool = pd.to_numeric(df.loc[idx, num_cols], errors="coerce").dropna().to_numpy(dtype=float)
        if _is_descriptive(text, number):
            continue
        value, dec = _scaled(text, number, value, dec)
        if _matches(row_pool, value, dec):
            continue
        others = pd.to_numeric(df.drop(index=idx).head(30)[num_cols].stack(), errors="coerce").dropna().to_numpy(float)
        if _matches(others, value, dec) and not _matches(derived_pool(row_pool), value, dec):
            bad.add(number.span(1))    # valor de OUTRO ativo atribuído a este
    return bad


def unverified_numbers(text: str, df: pd.DataFrame | None, context_lines: list[str] | None = None) -> list[str]:
    cand = _candidates(_values(df))
    ctx = np.array([_parse(m.group(1))[0] for l in (context_lines or []) for m in _NUM.finditer(l)])
    pool = np.concatenate([cand, ctx]) if len(ctx) else cand
    entity_bad = _entity_mismatches(text, df)
    bad: list[str] = []
    for m in _NUM.finditer(text):
        tok = m.group(1)
        v, dec = _parse(tok)
        if dec == 0 and 1990 <= v <= 2100:                    # anos são metadados, não medidas
            continue
        if _is_descriptive(text, m):
            continue
        v, dec = _scaled(text, m, v, dec)
        ok = _matches(pool, v, dec) and m.span(1) not in entity_bad
        if not ok and tok not in bad:
            bad.append(tok)
    return bad
