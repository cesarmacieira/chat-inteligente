"""Histórico persistente (SQLite): cada pergunta, a resposta e tudo o que foi executado para chegar nela.
No Streamlit Community Cloud o disco é efêmero: para guardar de forma permanente, aponte HISTORY_PATH para um volume."""
import json
import sqlite3
from datetime import datetime

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS turns(
  id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER NOT NULL REFERENCES conversations(id),
  ts TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, status TEXT NOT NULL,
  sql_final TEXT, attempts TEXT, rows INTEGER, columns TEXT, preview TEXT, attention TEXT, context TEXT,
  provider TEXT, model TEXT, secs REAL, error TEXT);
CREATE INDEX IF NOT EXISTS ix_turns_conv ON turns(conversation_id);
"""


def _con() -> sqlite3.Connection:
    config.HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.HISTORY_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def new_conversation(title: str) -> int:
    con = _con()
    try:
        cur = con.execute("INSERT INTO conversations(started_at, title) VALUES (?, ?)",
                          (datetime.now().isoformat(timespec="seconds"), title[:120]))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def log_turn(conv_id: int, question: str, answer: str, status: str, *, sql_final=None, attempts=None, df=None,
             attention=None, context=None, provider="", model="", secs=0.0, error=None) -> int:
    preview = None if df is None else df.head(50).to_json(orient="split", date_format="iso", force_ascii=False)
    con = _con()
    try:
        cur = con.execute(
            "INSERT INTO turns(conversation_id, ts, question, answer, status, sql_final, attempts, rows, columns, "
            "preview, attention, context, provider, model, secs, error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (conv_id, datetime.now().isoformat(timespec="seconds"), question, answer, status, sql_final,
             json.dumps(attempts or [], ensure_ascii=False), None if df is None else len(df),
             json.dumps(list(df.columns) if df is not None else [], ensure_ascii=False), preview,
             json.dumps(attention or [], ensure_ascii=False), json.dumps(context or [], ensure_ascii=False),
             provider, model, round(secs, 2), error))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def recent_conversations(n: int = 8) -> list[dict]:
    con = _con()
    try:
        rows = con.execute("""SELECT c.id, c.title, c.started_at, COUNT(t.id) AS n
            FROM conversations c JOIN turns t ON t.conversation_id = c.id
            GROUP BY c.id ORDER BY MAX(t.id) DESC LIMIT ?""", (n,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def conversation_turns(conv_id: int) -> list[dict]:
    con = _con()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM turns WHERE conversation_id = ? ORDER BY id", (conv_id,))]
    finally:
        con.close()


def all_turns(limit: int = 500, search: str = "") -> list[dict]:
    con = _con()
    try:
        q = ("SELECT t.*, c.title FROM turns t JOIN conversations c ON c.id = t.conversation_id "
             "WHERE (? = '' OR t.question LIKE '%'||?||'%' OR t.answer LIKE '%'||?||'%') ORDER BY t.id DESC LIMIT ?")
        return [dict(r) for r in con.execute(q, (search, search, search, limit))]
    finally:
        con.close()


def preview_df(turn: dict):
    import pandas as pd
    if not turn.get("preview"):
        return None
    return pd.read_json(__import__("io").StringIO(turn["preview"]), orient="split")
