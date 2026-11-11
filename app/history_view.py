"""Histórico: todas as perguntas, respostas e o que foi executado para chegar nelas."""
import json

import pandas as pd
import streamlit as st

from chat_inteligente import history
from chat_inteligente.labels import pretty_df
import chat_view


def render() -> None:
    q = st.text_input("Buscar no histórico", placeholder="palavra da pergunta ou da resposta", key="hist_q")
    turns = history.all_turns(500, q.strip())
    if not turns:
        st.info("Nenhuma pergunta registrada ainda. Use o chat e o registro aparece aqui.")
        return
    flat = pd.DataFrame([{"Data/hora": t["ts"], "Conversa": t["title"], "Pergunta": t["question"],
                          "Resposta": t["answer"], "Registros": t["rows"], "Situação": "Concluída" if t["status"] == "ok" else "Com erro",
                          "Consulta executada": t["sql_final"], "Modelo": f"{t['provider']} · {t['model']}",
                          "Tempo (s)": t["secs"]} for t in turns])
    st.download_button("Baixar histórico completo (CSV)", flat.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="historico_chat.csv", mime="text/csv", key="hist_dl")
    st.caption(f"{len(turns)} registro(s), do mais recente para o mais antigo.")
    for t in turns:
        mark = "" if t["status"] == "ok" else " ⚠"
        with st.expander(f"{t['ts'].replace('T', ' ')} · {t['question'][:90]}{mark}"):
            st.markdown(f"**Pergunta**\n\n{t['question']}")
            st.markdown(f"**Resposta**\n\n{t['answer']}")
            att = json.loads(t["attention"] or "[]")
            if att:
                st.markdown("**Pontos de atenção**\n\n" + "\n".join(f"- {a}" for a in att))
            df = history.preview_df(t)
            if df is not None and len(df):
                st.caption(f"Resultado ({t['rows']} registro(s); até 50 gravados)")
                st.dataframe(pretty_df(df), hide_index=True)
            st.markdown("**O que foi executado**")
            chat_view.technical_details(t["sql_final"], json.loads(t["attempts"] or "[]"), t["secs"], t["provider"],
                                        t["model"], t["error"])
            st.button("Continuar esta conversa", key=f"open_{t['id']}", on_click=chat_view.load_conversation,
                      args=(t["conversation_id"],))
