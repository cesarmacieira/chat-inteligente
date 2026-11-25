"""Página de chat para a diretoria: respostas em linguagem de negócio, tabelas formatadas, gráfico automático,
pontos de atenção visíveis e registro permanente de cada pergunta/resposta/consulta."""
import html
import io
import json
import logging
import re
import time

import pandas as pd
import streamlit as st

from chat_inteligente import briefing, config, history
from chat_inteligente.context import fmt_num
from chat_inteligente.labels import humanize, pretty_df
from chat_inteligente.prompt_guard import inspect_question
import charts

AVATAR = ":material/auto_awesome:"
logger = logging.getLogger(__name__)


def display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Compatível com o nome antigo: tabela pronta para exibir."""
    return pretty_df(df)


def history_for_llm(msgs: list[dict], n_turns: int = 3) -> list[dict]:
    """Últimas perguntas + SQL gerado, para perguntas de acompanhamento."""
    out = []
    pairs = []
    for i, m in enumerate(msgs):
        if m["role"] == "user":
            nxt = msgs[i + 1] if i + 1 < len(msgs) and msgs[i + 1]["role"] == "assistant" else {}
            if nxt.get("error") == "entrada_recusada" or inspect_question(m["text"]):
                continue
            pairs.append(m)
        elif m.get("sql") and m.get("error") != "entrada_recusada":
            pairs.append(m)
    for m in pairs[-2 * n_turns:]:
        out.append({"role": "user", "content": f"<pergunta_anterior>\n{m['text']}\n</pergunta_anterior>"}
                   if m["role"] == "user" else
                   {"role": "assistant", "content": f"<sql_anterior>\n```sql\n{m['sql']}\n```\n</sql_anterior>"})
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
    band = charts.find_band(df)
    if band:
        return charts.band_chart(df, *band), "band"
    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
            and str(c).lower() not in ("ano", "year", "mes", "trimestre", "semana")]
    if not nums:
        return None
    time_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])
                 or str(c).lower() in ("ano", "mes", "trimestre", "semana", "year")]
    cats = [c for c in df.columns if pd.api.types.is_string_dtype(df[c])]
    nice = {c: humanize(c) for c in df.columns}
    if time_cols:
        x = time_cols[0]
        if cats and df[cats[0]].nunique() <= 8 and len(nums) >= 1:
            # Nunca agrega silenciosamente: soma distorce taxas/concentrações e média distorce totais.
            if df.duplicated([x, cats[0]]).any():
                return None
            wide = df.pivot(index=x, columns=cats[0], values=nums[0]).sort_index()
            wide.index = wide.index.astype(str) if not pd.api.types.is_datetime64_any_dtype(wide.index) else wide.index
            return wide, "line"
        wide = df.set_index(x)[nums[:3]].sort_index().rename(columns=nice)
        wide.index = wide.index.astype(str) if not pd.api.types.is_datetime64_any_dtype(wide.index) else wide.index
        return wide, "line"
    if cats and len(df) <= 25 and df[cats[0]].is_unique:
        return df.set_index(cats[0])[nums[:1]].rename(columns=nice), "bar"
    return None


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(v, *, header=False):
    if not isinstance(v, str) or not v.startswith(_FORMULA_START):
        return v
    # Número negativo formatado pela própria aplicação não é fórmula; expressões como -2+3 continuam bloqueadas.
    if not header and re.fullmatch(r"-\d{1,3}(?:\.\d{3})*(?:,\d+)?|-\d+(?:,\d+)?", v):
        return v
    return "'" + v


def _defuse(df: pd.DataFrame) -> pd.DataFrame:
    """Neutraliza fórmulas em valores e cabeçalhos antes de exportar para planilhas."""
    out = df.copy()
    out.columns = [_safe_cell(str(c), header=True) for c in out.columns]
    for c in out.columns:
        if not pd.api.types.is_numeric_dtype(out[c]) and not pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].map(_safe_cell)
    return out


def _xlsx(df: pd.DataFrame) -> bytes:
    """Excel com tipos nativos; a apresentação pt-BR é aplicada como formato, não como texto."""
    out = _defuse(df)
    names, seen = [], {}
    for c in out.columns:
        name = humanize(c)
        seen[name] = seen.get(name, 0) + 1
        names.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    out.columns = names
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        out.to_excel(w, index=False, sheet_name="Resultado")
        ws = w.sheets["Resultado"]
        for i, (col, original) in enumerate(zip(out.columns, df.columns), start=1):
            s = df[original]
            width = max([len(str(col))] + [len(str(v)) for v in s.head(200)]) + 2
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(width, 60)
            if pd.api.types.is_datetime64_any_dtype(s):
                for cell in ws.iter_cols(min_col=i, max_col=i, min_row=2):
                    for value in cell: value.number_format = "dd/mm/yyyy"
            elif pd.api.types.is_integer_dtype(s):
                for cell in ws.iter_cols(min_col=i, max_col=i, min_row=2):
                    for value in cell: value.number_format = "#,##0"
            elif pd.api.types.is_float_dtype(s):
                for cell in ws.iter_cols(min_col=i, max_col=i, min_row=2):
                    for value in cell: value.number_format = "#,##0.00"
    return buf.getvalue()


def followups(df: pd.DataFrame | None, sql: str | None) -> list[str]:
    """Próximos passos sugeridos a partir do que a resposta mostrou (regras simples, sem custo de LLM)."""
    low = (sql or "").lower()
    if "v_forecasts" in low:
        out = ["Essa previsão costuma acertar?", "Compare com os últimos 30 dias"]
    elif "v_outliers" in low:
        out = ["Qual a tendência dessas séries nos últimos 90 dias?", "Houve outros desvios nos últimos 30 dias?"]
    elif "v_trends" in low:
        out = ["Quais dessas séries tiveram valor fora do padrão recentemente?", "Qual a previsão dos próximos 7 dias para elas?"]
    elif "producao_t" in low:
        out = ["Qual a previsão para os próximos 7 dias?", "Compare com o mesmo mês do ano anterior"]
    elif any(k in low for k in ("acidentes", "incidentes", "desvios", "ocorrencias")):
        out = ["Mostre a evolução mensal", "Qual a taxa por milhão de horas-homem?"]
    else:
        out = ["Mostre a evolução mensal", "Quais pontos merecem atenção?"]
    return out[:2] + ["Resuma em três pontos para a diretoria"]


def _show_table(df: pd.DataFrame, key: str, secs: float | None = None) -> None:
    n = len(df)
    meta = f"{fmt_num(n, 0)} registro{'s' if n != 1 else ''}" + (f" · {secs:.1f} s" if secs else "")
    st.markdown(f'<div class="meta">{meta}</div>', unsafe_allow_html=True)
    ch = chart_for(df)
    if ch is not None:
        data, kind = ch
        if kind == "band":
            st.altair_chart(data, width="stretch")
        else:
            (st.line_chart if kind == "line" else st.bar_chart)(data, height=260)
    st.dataframe(pretty_df(df), hide_index=True)
    pretty = pretty_df(df)
    c1, c2, _ = st.columns([1, 1, 3])
    c1.download_button("Baixar Excel", _xlsx(df), file_name="resultado.xlsx", key=f"xl_{key}",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    c2.download_button("Baixar CSV", _defuse(pretty).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
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


def _on_feedback(key: str, turn_id: int) -> None:
    try:
        history.set_feedback(turn_id, st.session_state.get(key))
    except Exception:
        logger.exception("Não foi possível gravar o feedback")


def _assistant(m: dict, key: str, latest: bool = False) -> None:
    with st.chat_message("assistant", avatar=AVATAR):
        st.markdown(m["text"])
        if m.get("attention"):
            st.markdown('<div class="attention"><b>Pontos de atenção</b><ul>'
                        + "".join(f"<li>{html.escape(l)}</li>" for l in m["attention"]) + "</ul></div>",
                        unsafe_allow_html=True)
        if m.get("df") is not None and len(m["df"]):
            _show_table(m["df"], key, m.get("secs"))
        if m.get("unverified"):
            st.markdown('<div class="meta">⚠ Não consegui conferir na tabela: ' + html.escape(", ".join(m["unverified"][:6]))
                        + ". Confirme esses números antes de usar.</div>", unsafe_allow_html=True)
        if m.get("turn_id"):
            fk = f"fb_{key}"
            st.feedback("thumbs", key=fk, on_change=_on_feedback, args=(fk, m["turn_id"]))
        if config.SHOW_TECHNICAL and (m.get("sql") or m.get("error")):
            with st.expander("Como chegamos a esse resultado"):
                technical_details(m.get("sql"), m.get("attempts"), m.get("secs"), m.get("provider", config.LLM_PROVIDER),
                                  m.get("model", ""), m.get("error"))
        if latest and m.get("df") is not None and len(m["df"]):
            st.caption("Continuar a análise")
            cols = st.columns(3)
            for i, q in enumerate(followups(m["df"], m.get("sql"))):
                cols[i].button(q, key=f"follow_{key}_{i}", on_click=_set_pending, args=(q,), width="stretch")


def load_conversation(conv_id: int) -> None:
    """Recarrega uma conversa gravada para continuar de onde parou."""
    ss = st.session_state
    msgs = []
    for t in history.conversation_turns(conv_id):
        msgs.append({"role": "user", "text": t["question"]})
        msgs.append({"role": "assistant", "text": t["answer"], "df": history.preview_df(t), "sql": t["sql_final"],
                     "attention": json.loads(t["attention"] or "[]"), "attempts": json.loads(t["attempts"] or "[]"),
                     "secs": t["secs"], "provider": t["provider"], "model": t["model"], "error": t["error"],
                     "turn_id": t["id"], "unverified": json.loads(t.get("unverified") or "[]")})
    ss.msgs, ss.conv_id, ss.view = msgs, conv_id, "chat"


@st.cache_data(ttl=600, show_spinner=False)
def _briefing_cached(run_ts: str) -> dict:
    return briefing.build()


def _briefing_text(info: dict) -> str:
    """Resumo determinístico, usado somente quando o usuário pedir."""
    if not info.get("has_run"):
        return "Os modelos ainda não foram executados; não há resumo do dia disponível."
    b = _briefing_cached(str(info.get("run_ts")))
    if not b["items"]:
        return "Não há pontos relevantes para destacar no resumo do dia."
    rows = "\n".join(f"- **{briefing.TAGS[k]}:** {text}" for k, text in b["items"])
    return f"Resumo do dia, com dados até {b['date']}:\n\n{rows}"


def _is_briefing_request(question: str) -> bool:
    q = " ".join(question.lower().strip().split())
    return q in {"resumo do dia", "mostre o resumo do dia", "mostrar resumo do dia", "briefing do dia"}


def render(info: dict, cat: dict) -> None:
    ss = st.session_state
    if not info["ok"]:
        st.info("Os dados ainda não foram carregados. Veja a barra lateral.")
        return

    typed = st.chat_input("Pergunte sobre produção, segurança ou meio ambiente...")
    question = typed or ss.pop("pending", None)
    if not ss.msgs and not question:
        st.markdown('<div class="welcome"><div class="welcome-mark">✦</div><h1>Como posso ajudar?</h1>'
                    '<p>Pergunte em português sobre produção, segurança e meio ambiente. '
                    'Eu busco os dados, resumo o resultado e destaco o que merece atenção.</p></div>',
                    unsafe_allow_html=True)
        with st.container(key="suggestions"):
            cols = st.columns(2)
            cols[0].button("Mostre o resumo do dia", key="daily_briefing", on_click=_set_pending,
                           args=("Mostre o resumo do dia",), width="stretch")
            for i, q in enumerate(cat.get("suggestions", [])[:8]):
                cols[i % 2].button(q, key=f"sug{i}", on_click=_set_pending, args=(q,), width="stretch")
    last_assistant = max((i for i, m in enumerate(ss.msgs) if m["role"] == "assistant"), default=-1)
    for i, m in enumerate(ss.msgs):
        _user(m["text"]) if m["role"] == "user" else _assistant(m, str(i), i == last_assistant)
    if not question:
        return

    hist = history_for_llm(ss.msgs)
    ss.msgs.append({"role": "user", "text": question})
    _user(question)
    model = config.OLLAMA_MODEL if config.LLM_PROVIDER == "ollama" else config.GROQ_MODEL
    t0 = time.time()
    with st.chat_message("assistant", avatar=AVATAR):
        with st.spinner("Consultando os dados..."):
            try:
                if _is_briefing_request(question):
                    msg = {"role": "assistant", "text": _briefing_text(info), "df": None, "sql": None,
                           "context": [], "attention": [], "attempts": [], "secs": time.time() - t0,
                           "error": None, "unverified": [], "provider": "local", "model": "resumo determinístico"}
                    status = "ok"
                else:
                    a = ss.agent.ask(question, hist)
                    msg = {"role": "assistant", "text": a.text, "df": a.df, "sql": a.sql, "context": a.context,
                           "attention": a.attention, "attempts": a.attempts, "secs": time.time() - t0, "error": a.error,
                           "unverified": a.unverified,
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
        msg["turn_id"] = history.log_turn(ss.conv_id, question, msg["text"], status, sql_final=msg.get("sql"), attempts=msg["attempts"],
                         df=msg["df"], attention=msg["attention"], context=msg["context"],
                         provider=config.LLM_PROVIDER, model=model, secs=msg["secs"], error=msg["error"],
                         unverified=msg.get("unverified"))
    except Exception:
        logger.exception("Não foi possível registrar a conversa no histórico")
    ss.msgs.append(msg)
    st.rerun()
