"""Gera dados fictícios de siderurgia (produção, segurança, meio ambiente) de 2021-01-01 até hoje.
Uso: python -m chat_inteligente.synth
"""
from .db import connect, reset_schema
from .sim.engine import build

SOURCE = "sintético (fictício) — gerado por chat_inteligente.synth"


def generate(start: str = "2021-01-01", end: str | None = None, seed: int = 2021) -> None:
    ents, cat, metrics = build(start, end, seed)
    con = connect()
    reset_schema(con)
    con.execute("INSERT INTO entities SELECT * FROM ents")
    con.execute("INSERT INTO metrics_catalog SELECT * FROM cat")
    con.execute("INSERT INTO daily_metrics SELECT entity_id, metric, ref_date::DATE, value FROM metrics")
    con.execute("INSERT INTO app_meta VALUES ('source', ?)", [SOURCE])
    con.close()


if __name__ == "__main__":
    generate()
    print("dados sintéticos gerados")
