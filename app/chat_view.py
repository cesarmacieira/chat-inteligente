"""Página de chat para a diretoria: respostas em linguagem de negócio, tabelas formatadas, gráfico automático,
pontos de atenção visíveis e registro permanente de cada pergunta/resposta/consulta."""
import html
import json
import time

import pandas as pd
import streamlit as st

from chat_inteligente import config, history
from chat_inteligente.context import fmt_num
from chat_inteligente.labels import humanize, pretty_df

AVATAR = ":material/auto_awesome:"


def display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Compatível com o nome antigo: tabela pronta para exibir."""
    return pretty_df(df)


def history_for_llm(msgs: list[dict], n_turns: int = 3) -> list[dict]:
    """Últimas perguntas + SQL gerado, para perguntas de acompanhamento."""
    out = []
    pairs = [m for m in msgs if m["role"] == "user" or m.get("sql")]
    for m in pairs[-2 * n_turns:]:
        out.append({"role": "user", "content": m["text"]} if m["role"] == "user"
                    else {"role": "assistant", "content": f"```sql\n{m['sql']}\n```"})
    return out


def _set_pending(q: str) -> None:
    st.session_state.pending = q


def _user(text: str) -> None:
    st.markdown(f'<div class="user-row"><div class="user-bubble">{html.escape(text)}</div></div>',
                unsafe_allow_html=True)


def chart_for(df: pd.DataFrame):
    """DataFrame pronto para gráfico (index = eixo X, colunas = séries) e o tipo ('line'|'bar'), ou None."""
    if df is None or len(df) < 3 or len(df) > 600:
        return None
    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
            and str(c).lower() not in ("ano", "year", "mes", "trimestre", "semana")]
    if not nums:
        return None
    time_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])
                 or str(c).lower() in ("ano", "mes", "trimestre", "semana", "year")]
    cats = [c for c in df.columns if df[c].dtype == object]
    nice = {c: humanize(c) for c in df.columns}
    if time_cols:
        x = time_cols[0]
        if cats and df[cats[0]].nunique() <= 8 and len(nums) >= 1:
            wide = df.pivot_table(index=x, columns=cats[0], values=nums[0], aggfunc="sum").sort_index()
            wide.index = wide.index.astype(str) if not pd.api.types.is_datetime64_any_dtype(wide.index) else wide.index
            return wide, "line"
        wide = df.set_index(x)[nums[:3]].sort_index().rename(columns=nice)
        wide.index = wide.index.astype(str) if not pd.api.types.is_datetime64_any_dtype(wide.index) else wide.index
        return wide, "line"
    if cats and len(df) <= 25 and df[cats[0]].is_unique:
        return df.set_index(cats[0])[nums[:1]].rename(columns=nice), "bar"
    return None


def _show_table(df: pd.DataFrame, key: str, secs: float | None = None) -> None:
    n = len(df)
    meta = f"{fmt_num(n, 0)} registro{'s' if n != 1 else ''}" + (f" · {secs:.1f} s" if secs else "")
    st.markdown(f'<div class="meta">{meta}</div>', unsafe_allow_html=True)
    ch = chart_for(df)
    if ch is not None:
        data, kind = ch
        (st.line_chart if kind == "line" else st.bar_chart)(data, height=260)
    st.dataframe(pretty_df(df), hide_index=True)
    st.download_button("Baixar tabela (CSV)", pretty_df(df).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="resultado.csv", mime="text/csv", key=f"dl_{key}")


def technical_details(sql, attempts, secs, provider, model, error=None) -> None:
    """Como o resultado foi obtido (auditoria): SQL, tentativas, tempo e modelo."""
    if sql:
        st.caption("Consulta executada no banco (somente leitura)")
        st.code(sql, language="sql")
    bad = [a for a in (attempts or []) if not a.get("ok")]
    if bad:
        st.caption(f"{len(bad)} tentativa(s) com erro corrigida(s) automaticamente")
        for a in bad:
            st.code(f"{a.get('sql', '')}\n-- erro: {a.get('error')}", language="sql")
    if error:
        st.caption(f"Erro: {error}")
    st.caption(f"Modelo: {provider} · {model} · {secs or 0:.1f} s")


def _assistant(m: dict, key: str) -> None:
    with st.chat_message("assistant", avatar=AVATAR):
        st.markdown(m["text"])
        if m.get("attention"):
            st.markdown('<div class="attention"><b>Pontos de atenção</b><ul>'
                        + "".join(f"<li>{html.escape(l)}</li>" for l in m["attention"]) + "</ul></div>",
                        unsafe_allow_html=True)
        if m.get("df") is not None and len(m["df"]):
            _show_table(m["df"], key, m.get("secs"))
        if config.SHOW_TECHNICAL and (m.get("sql") or m.get("error")):
            with st.expander("Como chegamos a esse resultado"):
                technical_details(m.get("sql"), m.get("attempts"), m.get("secs"), m.get("provider", config.LLM_PROVIDER),
                                  m.get("model", ""), m.get("error"))


def load_conversation(conv_id: int) -> None:
    """Recarrega uma conversa gravada para continuar de onde parou."""
    ss = st.session_state
    msgs = []
    for t in history.conversation_turns(conv_id):
        msgs.append({"role": "user", "text": t["question"]})
        msgs.append({"role": "assistant", "text": t["answer"], "df": history.preview_df(t), "sql": t["sql_final"],
                     "attention": json.loads(t["attention"] or "[]"), "attempts": json.loads(t["attempts"] or "[]"),
                     "secs": t["secs"], "provider": t["provider"], "model": t["model"], "error": t["error"]})
    ss.msgs, ss.conv_id, ss.view, ss.nq = msgs, conv_id, "chat", 0


def render(info: dict, cat: dict) -> None:
    ss = st.session_state
    if not info["ok"]:
        st.info("Os dados ainda não foram carregados. Veja a barra lateral.")
        return

    typed = st.chat_input("Pergunte sobre produção, segurança ou meio ambiente...")
    question = typed or ss.pop("pending", None)
    if question and config.MAX_QUESTIONS and ss.get("nq", 0) >= config.MAX_QUESTIONS:
        st.warning(f"Limite de {config.MAX_QUESTIONS} perguntas por sessão atingido. Use «Nova conversa» ou recarregue a página.")
        question = None

    if not ss.msgs and not question:
        st.markdown('<div class="welcome"><div class="welcome-mark">✦</div><h1>Como posso ajudar?</h1>'
                    '<p>Pergunte em português sobre produção, segurança e meio ambiente. '
                    'Eu busco os dados, resumo o resultado e destaco o que merece atenção.</p></div>',
                    unsafe_allow_html=True)
        with st.container(key="suggestions"):
            cols = st.columns(2)
            for i, q in enumerate(cat.get("suggestions", [])[:8]):
                cols[i % 2].button(q, key=f"sug{i}", on_click=_set_pending, args=(q,), width="stretch")
    for i, m in enumerate(ss.msgs):
        _user(m["text"]) if m["role"] == "user" else _assistant(m, str(i))
    if not question:
        return

    ss.nq = ss.get("nq", 0) + 1
    hist = history_for_llm(ss.msgs)
    ss.msgs.append({"role": "user", "text": question})
    _user(question)
    model = config.OLLAMA_MODEL if config.LLM_PROVIDER == "ollama" else config.GROQ_MODEL
    t0 = time.time()
    with st.chat_message("assistant", avatar=AVATAR):
        with st.spinner("Consultando os dados..."):
            try:
                a = ss.agent.ask(question, hist)
                msg = {"role": "assistant", "text": a.text, "df": a.df, "sql": a.sql, "context": a.context,
                       "attention": a.attention, "attempts": a.attempts, "secs": time.time() - t0, "error": a.error,
                       "provider": config.LLM_PROVIDER, "model": model}
                status = "erro" if a.error else "ok"
            except Exception as e:  # falha de rede, limite do provedor etc.
                msg = {"role": "assistant", "df": None, "sql": None, "context": [], "attention": [], "attempts": [],
                       "secs": time.time() - t0, "error": str(e), "provider": config.LLM_PROVIDER, "model": model,
                       "text": "Não consegui concluir a consulta agora. Aguarde alguns segundos e tente novamente."}
                status = "erro"
    try:  # o registro nunca pode derrubar o chat
        if ss.get("conv_id") is None:
            ss.conv_id = history.new_conversation(question)
        history.log_turn(ss.conv_id, question, msg["text"], status, sql_final=msg.get("sql"), attempts=msg["attempts"],
                         df=msg["df"], attention=msg["attention"], context=msg["context"],
                         provider=config.LLM_PROVIDER, model=model, secs=msg["secs"], error=msg["error"])
    except Exception:
        pass
    ss.msgs.append(msg)
    st.rerun()
