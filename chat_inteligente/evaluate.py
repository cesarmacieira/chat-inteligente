"""Avaliação do chat com o LLM configurado: roda as perguntas de evals/golden.yaml e compara o resultado de cada
uma com o SQL de referência (a ordem e os apelidos das colunas não importam; valores e número de linhas, sim).

Uso: python -m chat_inteligente.evaluate [--limit N]
Gasta chamadas do LLM (duas por pergunta). Serve para comparar modelos e prompts antes de uma mudança."""
import argparse
import time

import numpy as np
import pandas as pd
import yaml

from . import config
from .agent import Agent, load_catalog
from .db import connect
from .sql_guard import validate

GOLDEN = config.ROOT / "evals" / "golden.yaml"


def load_golden() -> list[dict]:
    return yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))


def reference_df(item: dict, cat: dict) -> pd.DataFrame:
    sql = item.get("sql") or next(e["sql"] for e in cat["examples"] if e["q"] == item["ref"])
    con = connect(read_only=True)
    try:
        return con.execute(validate(sql.strip().rstrip(";"), {t.lower() for t in cat["tables"]}, config.MAX_ROWS)).df()
    finally:
        con.close()


def _row_parts(row: pd.Series) -> tuple[list[float], list[str]]:
    nums, texts = [], []
    for value in row:
        if pd.isna(value):
            continue
        if isinstance(value, (int, float, np.number)) and not isinstance(value, (bool, np.bool_)):
            nums.append(float(value))
        else:
            texts.append(str(value))
    return nums, texts


def _row_contains(got: pd.Series, ref: pd.Series, rtol: float) -> bool:
    """Aliases e colunas extras podem mudar, mas dimensões e medidas devem ficar na mesma linha."""
    gn, gt = _row_parts(got)
    rn, rt = _row_parts(ref)
    if not set(rt) <= set(gt):
        return False
    pool = list(gn)
    for value in rn:
        idx = next((i for i, candidate in enumerate(pool)
                    if abs(candidate - value) <= rtol * max(1.0, abs(value))), None)
        if idx is None:
            return False
        pool.pop(idx)
    return True


def same_result(got: pd.DataFrame | None, ref: pd.DataFrame, rtol: float = 1e-6) -> tuple[bool, str]:
    if got is None:
        return False, "sem resultado"
    if len(got) != len(ref):
        return False, f"{len(got)} linhas, esperado {len(ref)}"
    remaining = list(range(len(got)))
    for _, ref_row in ref.iterrows():
        match = next((i for i in remaining if _row_contains(got.iloc[i], ref_row, rtol)), None)
        if match is None:
            return False, "linha de referência ausente ou valores associados à dimensão errada"
        remaining.remove(match)
    return True, "ok"


def run(agent: Agent, items: list[dict] | None = None, limit: int | None = None) -> list[dict]:
    cat = load_catalog()
    out = []
    for item in (items or load_golden())[:limit]:
        t0 = time.time()
        try:
            a = agent.ask(item["q"])
            ok, why = same_result(a.df, reference_df(item, cat))
            if a.error:
                ok, why = False, a.error
        except Exception as e:
            ok, why = False, f"exceção: {e}"
        out.append({"q": item["q"], "ok": ok, "why": why, "secs": round(time.time() - t0, 1)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    res = run(Agent(), limit=ap.parse_args().limit)
    for r in res:
        print(f"{'OK ' if r['ok'] else 'ERRO'} {r['secs']:>5}s  {r['q']}" + ("" if r["ok"] else f"  -> {r['why']}"))
    print(f"\nAcertos: {sum(r['ok'] for r in res)}/{len(res)} ({config.LLM_PROVIDER})")


if __name__ == "__main__":
    main()
