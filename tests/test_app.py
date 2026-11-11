from pathlib import Path
from chat_inteligente.db import connect
from chat_inteligente.sql_guard import validate
from chat_inteligente.agent import load_catalog

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")
ALLOWED = {t.lower() for t in load_catalog()["tables"]}


def test_catalog_examples_execute():
    con = connect(read_only=True)
    try:
        for ex in load_catalog()["examples"]:
            df = con.execute(validate(ex["sql"].strip().rstrip(";"), ALLOWED, 50)).df()
            assert len(df) > 0, ex["q"]
    finally:
        con.close()


def test_every_suggestion_has_an_example():
    cat = load_catalog()
    assert set(cat["suggestions"]) <= {e["q"] for e in cat["examples"]}


def _fake_llm(monkeypatch, sql="SELECT planta, COUNT(*) c FROM entities GROUP BY 1"):
    import chat_inteligente.agent as agent

    class Fake:
        def chat(self, m):
            return f"```sql\n{sql}\n```"
    monkeypatch.setattr(agent, "get_llm", lambda: Fake())


def _go(at, view):
    at.button(key=f"nav_{view}").click().run()
    assert not at.exception, at.exception
    return at


def test_chat_page_welcome_and_suggestion_click(monkeypatch):
    from streamlit.testing.v1 import AppTest
    _fake_llm(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception, at.exception
    assert any("fictícios" in m.value for m in at.sidebar.markdown)
    assert len(at.chat_input) == 1 and len(at.tabs) == 0         # caixa de pergunta no nível da página (fica fixa no rodapé)
    sugs = [b for b in at.button if str(b.key).startswith("sug")]
    assert len(sugs) >= 8
    sugs[0].click().run()
    assert not at.exception, at.exception
    assert len(at.chat_message) >= 1
    assert not [b for b in at.button if str(b.key).startswith("sug")]   # boas-vindas some após a 1ª pergunta
    at.button(key="new_chat").click().run()
    assert len(at.chat_message) == 0 and any(str(b.key).startswith("sug") for b in at.button)


def test_chat_input_flow_shows_context_and_sql(monkeypatch):
    from streamlit.testing.v1 import AppTest
    _fake_llm(monkeypatch, "SELECT e.name, d.value FROM daily_metrics d JOIN entities e USING (entity_id) "
                           "WHERE d.metric='producao_t' AND d.ref_date = DATE '2026-11-05'")
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.chat_input[0].set_value("produção em 05/11/2026").run()
    assert not at.exception, at.exception
    assert len(at.chat_message) == 1
    assert any("Como chegamos" in e.label for e in at.expander)
    assert any("Pontos de atenção" in m.value for m in at.markdown)        # visível, sem abrir nada
    cols = list(at.dataframe[0].value.columns)
    assert cols == ["Ativo", "Valor"] and "." in at.dataframe[0].value["Valor"].iloc[0] + "."   # títulos em português
    from chat_inteligente import history                                  # e tudo ficou gravado
    t = history.all_turns(5, "05/11/2026")[0]
    assert t["status"] == "ok" and "producao_t" in t["sql_final"] and t["rows"] > 0 and t["answer"]


def test_navigation_views_render(monkeypatch):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=120).run()
    _go(at, "analises")
    assert len(at.tabs) >= 6 and len(at.chat_input) == 0
    _go(at, "dados")
    assert at.selectbox(key="dt_tbl")
    _go(at, "sobre")
    assert any("simulados" in w.value for w in at.warning)
    _go(at, "chat")
    assert len(at.chat_input) == 1


def test_analysis_filters_do_not_break():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=120).run()
    _go(at, "analises")
    for key, val in [("per_exec", "Todo o período"), ("per_prod", "Últimos 30 dias"),
                     ("per_seg", "Ano atual"), ("per_amb", "Últimos 90 dias"),
                     ("ml_win", 365), ("det_met", "acidentes")]:
        at.selectbox(key=key).select(val).run()
        assert not at.exception, (key, at.exception)
    at.radio(key="prod_nivel").set_value("Planta").run()
    assert not at.exception


def test_data_tab_filters():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=120).run()
    _go(at, "dados")
    at.selectbox(key="dt_tbl").select("v_outliers").run()
    at.checkbox(key="dt_out").check().run()
    assert not at.exception
    at.selectbox(key="dt_tbl").select("ml_runs").run()
    assert not at.exception


def test_display_df_formats_dates_and_floats():
    import sys, pandas as pd
    sys.path.insert(0, str(Path(APP).parent))
    import chat_view
    df = pd.DataFrame({"d": pd.to_datetime(["2026-11-05"]), "v": [1203.123456], "n": ["x"]})
    out = chat_view.display_df(df)
    assert out["D"].iloc[0] == "05/11/2026" and out["V"].iloc[0] == "1.203,1"


def test_bootstrap_noop_without_flag(monkeypatch):
    from chat_inteligente import bootstrap, config
    monkeypatch.setattr(config, "AUTO_BOOTSTRAP", False)
    assert bootstrap.ensure_data() is False


def test_bootstrap_builds_missing_db(monkeypatch):
    import tempfile
    from chat_inteligente import bootstrap, config, overview
    old = config.DB_PATH
    try:
        config.DB_PATH = Path(tempfile.mkdtemp()) / "novo.duckdb"
        monkeypatch.setattr(config, "AUTO_BOOTSTRAP", True)
        assert not overview.status()["ok"]
        assert bootstrap.ensure_data() is True
        s = overview.status()
        assert s["ok"] and s["has_run"]
        assert bootstrap.ensure_data() is False       # segunda chamada não refaz
    finally:
        config.DB_PATH = old


def test_password_gate_and_question_limit(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from chat_inteligente import config
    monkeypatch.setattr(config, "APP_PASSWORD", "segredo")
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception and len(at.chat_input) == 0 and len(at.sidebar.button) == 0   # bloqueado
    at.text_input(key="pwd").input("errada")
    at.button[0].click().run()
    assert any("incorreta" in e.value for e in at.error) and len(at.chat_input) == 0
    at.text_input(key="pwd").input("segredo")
    at.button[0].click().run()
    assert not at.exception and len(at.chat_input) == 1

    _fake_llm(monkeypatch, "SELECT COUNT(*) c FROM entities")
    monkeypatch.setattr(config, "APP_PASSWORD", "")
    monkeypatch.setattr(config, "MAX_QUESTIONS", 1)
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.chat_input[0].set_value("quantos ativos?").run()
    at.chat_input[0].set_value("e agora?").run()
    assert any("Limite" in w.value for w in at.warning)


def test_load_table_counts():
    from chat_inteligente import overview
    df, total = overview.load_table("v_outliers", only_outliers=True)
    assert total == len(df) > 0 and df["is_outlier"].all() and "ativo" in df.columns
    df2, _ = overview.load_table("daily_metrics", metric="acidentes")
    assert set(df2["metric"]) == {"acidentes"}


def test_history_view_and_resume(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from chat_inteligente import history
    _fake_llm(monkeypatch)
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.chat_input[0].set_value("quantas entidades por planta?").run()
    assert not at.exception, at.exception
    _go(at, "historico")
    assert any("quantas entidades por planta?" in e.label for e in at.expander)
    n = len(history.all_turns(1000))
    at2 = AppTest.from_file(APP, default_timeout=120).run()               # nova sessão: conversa aparece na lateral
    rec = [b for b in at2.sidebar.button if str(b.key).startswith("hist_")]
    assert rec
    rec[0].click().run()
    assert not at2.exception, at2.exception
    assert len(at2.chat_message) >= 1 and len(history.all_turns(1000)) == n   # só leitura, não regrava


def test_outlier_question_on_normal_day_returns_row():
    con = connect(read_only=True)
    try:
        sql = [e["sql"] for e in load_catalog()["examples"] if "foi um outlier" in e["q"]][0]
        df = con.execute(sql.replace("2026-09-19", "2025-12-28")).df()   # dia comum, fora da janela de 90 dias
        assert len(df) >= 1 and not df["Fora do padrão"].any()
    finally:
        con.close()
