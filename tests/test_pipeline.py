import pytest
from chat_inteligente.db import connect
from chat_inteligente.sql_guard import validate, UnsafeSQL
from chat_inteligente.agent import Agent, live_context, load_catalog

ALLOWED = {t.lower() for t in load_catalog()["tables"]}


def q(sql):
    con = connect(read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_data_shape():
    assert q("SELECT MIN(ref_date), MAX(ref_date) FROM daily_metrics")[0][0].isoformat() == "2021-01-01"
    assert q("SELECT MAX(ref_date) FROM daily_metrics")[0][0].isoformat() == "2026-11-09"
    areas = {r[0] for r in q("SELECT DISTINCT area FROM metrics_catalog")}
    assert areas == {"producao", "seguranca", "meio_ambiente"}
    assert q("SELECT COUNT(*) FROM daily_metrics WHERE value IS NULL")[0][0] == 0


def test_no_negative_physical_values():
    assert q("""SELECT COUNT(*) FROM daily_metrics d JOIN metrics_catalog c USING (metric)
                WHERE d.value < 0 AND c.metric <> 'ph_efluente'""")[0][0] == 0


def test_seg00_is_sum_of_areas():
    a = q("SELECT SUM(value) FROM daily_metrics WHERE metric='acidentes' AND entity_id='SEG00'")[0][0]
    b = q("""SELECT SUM(d.value) FROM daily_metrics d JOIN entities e USING (entity_id)
             WHERE d.metric='acidentes' AND e.tipo <> 'consolidado_seguranca'""")[0][0]
    assert a == b


def test_ml_tables_populated():
    assert q("SELECT COUNT(*) FROM v_outliers WHERE is_outlier")[0][0] > 0
    assert q("SELECT COUNT(*) FROM v_trends WHERE trend_direction IN ('alta','queda')")[0][0] > 0
    assert {r[0] for r in q("SELECT DISTINCT window_days FROM v_trends")} == {30, 90, 365}


def test_planted_stories_detected():
    # deriva de particulados do AF02, óleos da ETE02 e queda de desvios da MAN01 (janela anual)
    def has(eid, metric, w, d):
        return q(f"SELECT COUNT(*) FROM v_trends WHERE entity_id='{eid}' AND metric='{metric}' "
                 f"AND window_days={w} AND trend_direction='{d}'")[0][0] == 1
    assert has("AF02", "emissao_particulados_mg_nm3", 90, "alta")
    assert has("ETE02", "oleos_graxas_mg_l", 90, "alta")
    assert has("MAN01", "desvios", 365, "queda")


def test_no_trend_on_sparse_counts():
    assert q("""SELECT COUNT(*) FROM v_trends t JOIN metrics_catalog c USING (metric)
                WHERE c.metric='acidentes' AND t.window_days=30 AND t.trend_direction <> 'estavel'""")[0][0] == 0


def test_outlier_rate_reasonable():
    n, k = q("SELECT COUNT(*), SUM(is_outlier::INT) FROM v_outliers WHERE ref_date > DATE '2026-11-09' - 90")[0]
    assert 0 < k / n < 0.02


def test_guard_ok_and_limit():
    assert "LIMIT 50" in validate("SELECT * FROM v_trends", ALLOWED, 50)


@pytest.mark.parametrize("sql", [
    "DROP TABLE entities", "SELECT * FROM ml_runs", "SELECT * FROM app_meta", "SELECT 1; SELECT 2",
    "SELECT * FROM read_csv('x.csv')", "DELETE FROM daily_metrics"])
def test_guard_blocks(sql):
    with pytest.raises(UnsafeSQL):
        validate(sql, ALLOWED, 50)


def test_live_context_lists_entities_and_metrics():
    t = live_context()
    assert "AF01" in t and "acidentes" in t and "2026-11-09" in t


class FakeLLM:
    def __init__(self):
        self.n = 0
        self.systems = []

    def chat(self, m):
        self.n += 1
        self.systems.append(m[0]["content"])
        if self.n == 1:
            return "```sql\nSELECT * FROM nao_existe\n```"
        if self.n == 2:
            return "```sql\nSELECT e.planta, COUNT(*) c FROM v_outliers JOIN entities e USING(entity_id) GROUP BY 1\n```"
        return "resumo"


def test_agent_retry_and_live_context():
    llm = FakeLLM()
    a = Agent(llm=llm).ask("outliers por planta?")
    assert a.error is None and len(a.df) > 0
    assert "DADOS DISPONÍVEIS" in llm.systems[0]


def test_empty_result_does_not_call_summary_llm():
    class L:
        def __init__(self): self.calls = 0
        def chat(self, m):
            self.calls += 1
            return "```sql\nSELECT name FROM entities WHERE name = 'x'\n```"
    llm = L()
    a = Agent(llm=llm).ask("?")
    assert llm.calls == 1 and "nenhuma linha" in a.text


def test_llm_providers_use_configured_endpoint_and_key(monkeypatch):
    from unittest import mock
    from chat_inteligente import config, llm
    ok = mock.Mock(status_code=200)
    ok.json.return_value = {"choices": [{"message": {"content": "a"}}], "message": {"content": "b"}}
    monkeypatch.setattr(config, "GROQ_API_KEY", "k1")
    monkeypatch.setattr(config, "GROQ_MODEL", "m1")
    with mock.patch("requests.post", return_value=ok) as post:
        assert llm.Groq().chat([]) == "a"
        assert post.call_args.args[0] == "https://api.groq.com/openai/v1/chat/completions"
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer k1"
        assert post.call_args.kwargs["json"]["model"] == "m1"
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        llm.Groq().chat([])
    monkeypatch.setattr(config, "OLLAMA_URL", "https://ollama.com")
    monkeypatch.setattr(config, "OLLAMA_API_KEY", "k2")
    with mock.patch("requests.post", return_value=ok) as post:
        assert llm.Ollama().chat([]) == "b"
        assert post.call_args.args[0] == "https://ollama.com/api/chat"
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer k2"


def test_no_openai_left_in_code():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    for f in list((root / "chat_inteligente").glob("*.py")) + list((root / "app").glob("*.py")) \
            + [root / ".env.example", root / ".streamlit" / "secrets.toml.example"]:
        assert "openai.com" not in f.read_text(encoding="utf-8").replace("api.groq.com/openai", "")
        assert "OPENAI_API_KEY" not in f.read_text(encoding="utf-8")


def test_429_is_retried_then_succeeds(monkeypatch):
    from unittest import mock
    from chat_inteligente import config, llm
    monkeypatch.setattr(config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    lim = mock.Mock(status_code=429, text='{"error":{"message":"Please try again in 14.9s."}}', headers={})
    ok = mock.Mock(status_code=200)
    ok.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    with mock.patch("requests.post", side_effect=[lim, ok]) as post:
        assert llm.Groq().chat([]) == "ok" and post.call_count == 2
    with mock.patch("requests.post", side_effect=[lim, lim, lim]) as post:
        with pytest.raises(RuntimeError, match="429"):
            llm.Groq().chat([])
        assert post.call_count == 3


def test_prompt_picks_relevant_examples_and_is_smaller():
    from chat_inteligente.agent import catalog_prompt, pick_examples
    cat = load_catalog()
    ex = pick_examples(cat, "quantos acidentes por área em 2026?", 4)
    assert len(ex) == 4 and any("acidentes" in e["q"].lower() for e in ex)
    assert len(catalog_prompt(cat, "acidentes 2026")) < len(catalog_prompt(cat))


def test_context_is_scoped_to_entities_in_result():
    import pandas as pd
    from chat_inteligente import context
    df = pd.DataFrame({"name": ["Linha de Galvanização 1"], "producao_t": [1203.0]})
    lines = context.build("SELECT * FROM daily_metrics WHERE metric='producao_t'", df)
    assert lines and lines[0].startswith("producao_t:") and "t/dia" in lines[0]
    assert all("Alto-Forno" not in l for l in lines[1:])
    assert context.build("SELECT 1") == []
    assert context.fmt_num(1203.5, 0) == "1.204" or context.fmt_num(1203.5, 0) == "1.203"
    assert context.fmt_num(1234567.891) == "1.234.567,89"


def test_agent_answer_has_context_and_specific_prompt():
    class L:
        def __init__(self): self.msgs = []
        def chat(self, m):
            self.msgs.append(m)
            return ("```sql\nSELECT e.name, d.value AS producao_t FROM daily_metrics d JOIN entities e USING (entity_id) "
                    "WHERE d.metric='producao_t' AND e.tipo='galvanizacao' AND d.ref_date = DATE '2026-11-05'\n```")
    llm = L()
    a = Agent(llm=llm).ask("produção da galvanização em 05/11/2026?")
    assert a.context and a.context[0].startswith("producao_t:")
    summary_call = llm.msgs[-1]
    assert "NOME de cada ativo" in summary_call[0]["content"]
    assert "CONTEXTO" in summary_call[1]["content"] and "Colunas:" in summary_call[1]["content"]


def test_labels_pretty_df():
    import pandas as pd
    from chat_inteligente.labels import pretty_df, clean_text
    df = pd.DataFrame({"name": ["AF1"], "ref_date": pd.to_datetime(["2026-11-05"]), "producao_t": [5301.234],
                       "ano": [2025], "metric": ["taxa_rejeicao_pct"], "is_outlier": [True]})
    out = pretty_df(df)
    assert list(out.columns) == ["Ativo", "Data", "Produção (t)", "Ano", "Indicador", "Fora do padrão"]
    r = out.iloc[0]
    assert r["Data"] == "05/11/2026" and r["Produção (t)"] == "5.301,2" and r["Ano"] == "2025"
    assert r["Indicador"] == "Taxa de rejeição (%)" and r["Fora do padrão"] == "Sim"
    assert "taxa_rejeicao_pct" not in clean_text("a taxa_rejeicao_pct subiu")


def test_every_metric_has_friendly_label():
    from chat_inteligente.labels import METRIC_LABELS
    from chat_inteligente.sim.profiles import METRICS
    assert {m[0] for m in METRICS} <= set(METRIC_LABELS)


def test_friendly_attention_has_no_jargon():
    from chat_inteligente import context
    lines = context.build("SELECT 1 FROM daily_metrics WHERE metric='producao_t'", friendly=True)
    assert lines and all("score" not in l and "producao_t" not in l for l in lines)


def test_agent_records_attempts_and_secs():
    class LLM:
        def __init__(self): self.n = 0
        def chat(self, m):
            self.n += 1
            return "```sql\nSELECT x FROM nada\n```" if self.n == 1 else "```sql\nSELECT name FROM entities\n```"
    a = Agent(llm=LLM()).ask("lista ativos")
    assert [t["ok"] for t in a.attempts][:2] == [False, True] and a.attempts[0]["error"] and a.secs >= 0


def test_history_roundtrip():
    import pandas as pd
    from chat_inteligente import history
    cid = history.new_conversation("teste de histórico")
    history.log_turn(cid, "pergunta?", "resposta", "ok", sql_final="SELECT 1", attempts=[{"sql": "SELECT 1", "ok": True}],
                     df=pd.DataFrame({"a": [1, 2]}), attention=["x"], provider="groq", model="m", secs=1.234)
    t = history.conversation_turns(cid)[0]
    assert t["question"] == "pergunta?" and t["rows"] == 2 and t["secs"] == 1.23
    assert list(history.preview_df(t)["a"]) == [1, 2]
    assert any(c["id"] == cid for c in history.recent_conversations(20))


def test_chart_for_shapes():
    import pandas as pd, sys
    sys.path.insert(0, "app")
    from chat_view import chart_for
    ts = pd.DataFrame({"ref_date": pd.date_range("2026-01-01", periods=5), "v": range(5)})
    assert chart_for(ts)[1] == "line"
    cat = pd.DataFrame({"name": list("abc"), "v": [3, 2, 1]})
    assert chart_for(cat)[1] == "bar"
    assert chart_for(cat.head(1)) is None
