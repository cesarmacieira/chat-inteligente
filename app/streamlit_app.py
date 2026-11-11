import hmac
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from chat_inteligente import bootstrap, config, history, overview
from chat_inteligente.agent import Agent, load_catalog
import analises
import chat_view
import history_view
import pages_extra
import theme

st.set_page_config(page_title="Chat inteligente", page_icon="✦", layout="wide", initial_sidebar_state="auto")
theme.apply()

if config.APP_PASSWORD and not st.session_state.get("auth"):
    theme.login_css()
    st.markdown('<div class="login-hero"><div class="welcome-mark">✦</div><h1>Chat inteligente</h1>'
                '<p>Produção, segurança e meio ambiente em linguagem simples.<br>Acesso restrito: informe a senha para entrar.</p></div>',
                unsafe_allow_html=True)
    with st.form("login", border=False):
        pwd = st.text_input("Senha de acesso", type="password", key="pwd", placeholder="Digite a senha")
        entrar = st.form_submit_button("Entrar", type="primary", width="stretch")
    if entrar or pwd:
        if hmac.compare_digest(pwd.encode(), config.APP_PASSWORD.encode()):
            st.session_state.auth = True
            st.rerun()
        elif entrar:
            st.error("Senha incorreta. Tente novamente.")
    st.markdown('<div class="login-foot">Dados fictícios de demonstração · acesso monitorado</div>', unsafe_allow_html=True)
    st.stop()


@st.cache_resource(show_spinner="Preparando os dados (primeira execução)...")
def _prepare() -> bool:
    return bootstrap.ensure_data()


_prepare()

ss = st.session_state
if "agent" not in ss:
    ss.agent = Agent()
    ss.msgs = []
    ss.conv_id = None
    ss.view = "chat"
cat = load_catalog()
info = overview.status()

VIEWS = {"chat": (":material/chat_bubble:", "Chat"), "analises": (":material/bar_chart:", "Análises"),
         "historico": (":material/history:", "Histórico"), "dados": (":material/table_chart:", "Dados"),
         "sobre": (":material/info:", "Sobre os dados")}


def _go(view: str) -> None:
    ss.view = view


def _new_chat() -> None:
    ss.msgs = []
    ss.conv_id = None
    ss.nq = 0
    ss.view = "chat"


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-mark">✦</div><div><div class="brand-name">Chat inteligente</div>'
                '<div class="brand-tag">Produção · Segurança · Meio ambiente</div></div></div>', unsafe_allow_html=True)
    st.button("Nova conversa", icon=":material/add:", key="new_chat", on_click=_new_chat, width="stretch")
    for key, (icon, label) in VIEWS.items():
        st.button(label, icon=icon, key=f"nav_{key}", on_click=_go, args=(key,), width="stretch",
                  type="primary" if ss.view == key else "secondary")
    try:
        recents = history.recent_conversations(6)
    except Exception:
        recents = []
    if recents:
        st.markdown('<div class="side-label">Conversas recentes</div>', unsafe_allow_html=True)
        for c in recents:
            lab = c["title"] if len(c["title"]) <= 34 else c["title"][:33] + "…"
            st.button(lab, key=f"hist_{c['id']}", on_click=chat_view.load_conversation, args=(c["id"],),
                      width="stretch", help=f"{c['started_at'].replace('T', ' ')} · {c['n']} pergunta(s)")

    if not info["ok"]:
        st.error("Banco não encontrado ou vazio.")
        st.code("python -m chat_inteligente.synth\npython -m chat_inteligente.run_daily")
        st.caption(info["reason"])
    else:
        src = info["source"]
        dot, status = ("side-dot", "Dados carregados")
        if info["has_run"] and info["stale"]:
            dot, status = "side-dot off", "Modelos desatualizados"
        elif not info["has_run"]:
            dot, status = "side-dot off", "Modelos ainda não rodaram"
        card = (f'<span class="{dot}"></span><b>{status}</b><br>'
                f"{info['n_entities']} ativos · {info['n_series']} séries<br>"
                f"{info['date_min']} a {info['date_max']}")
        if info["has_run"]:
            card += f"<br>Modelos rodaram em {info['run_ts']}"
        st.markdown(f'<div class="side-card">{card}</div>', unsafe_allow_html=True)
        if src and src.startswith("sint"):
            st.markdown('<div class="side-note">⚠ Dados <b>fictícios</b> de demonstração.</div>', unsafe_allow_html=True)
        elif src:
            st.markdown(f'<div class="side-note">Fonte: {src}</div>', unsafe_allow_html=True)
        if not info["has_run"] or info.get("stale"):
            st.caption("Rode `python -m chat_inteligente.run_daily`.")
    st.markdown(f'<div class="side-note">LLM: {config.LLM_PROVIDER} · '
                f'{config.OLLAMA_MODEL if config.LLM_PROVIDER == "ollama" else config.GROQ_MODEL}<br>'
                'Toda pergunta e resposta fica registrada em «Histórico».</div>', unsafe_allow_html=True)

# --------------------------------------------------------------------- conteúdo
model_name = config.OLLAMA_MODEL if config.LLM_PROVIDER == "ollama" else config.GROQ_MODEL
if ss.view == "chat":
    theme.header('Chat <span>inteligente</span>', f"Dados até {info['date_max']}" if info["ok"] else "")
    chat_view.render(info, cat)
else:
    icon, label = VIEWS[ss.view]
    theme.header(f'Chat <span>inteligente</span> · {label}')
    if ss.view == "analises":
        theme.view_title("Análises", "Produção, segurança e meio ambiente, com anomalias e tendências dos modelos de ML.")
        if not (info["ok"] and info["has_run"]):
            st.info("Gere os dados e rode os modelos para ver as análises.")
        else:
            s1, s2, s3, s4, s5, s6 = st.tabs(["Visão executiva", "Produção", "Segurança", "Meio ambiente",
                                             "Anomalias e tendências (ML)", "Série em detalhe"])
            with s1:
                analises.executiva(info)
            with s2:
                analises.producao(info)
            with s3:
                analises.seguranca(info)
            with s4:
                analises.ambiente(info)
            with s5:
                analises.modelos(info)
            with s6:
                analises.detalhe(info)
    elif ss.view == "historico":
        theme.view_title("Histórico", "Todas as perguntas, as respostas e o que foi executado para chegar a cada uma.")
        history_view.render()
    elif ss.view == "dados":
        theme.view_title("Dados", "Tabelas base e resultados dos modelos.")
        pages_extra.dados(info)
    else:
        theme.view_title("Sobre os dados", "Contexto, fluxo, modelos e referências.")
        pages_extra.sobre(info, cat)
