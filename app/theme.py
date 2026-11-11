"""Design system do app (inspirado no Chat GPTrem da JFCE e no layout do ChatGPT).

Para mudar a identidade visual, edite só as variáveis de :root (--accent e cia.).
"""
import streamlit as st

CSS = """
<style>
:root{--ink:#1f2328;--muted:#6b7280;--line:#e5e7eb;--accent:#1f5f8b;--accent-dark:#164766;
  --accent-soft:#e8f0f7;--canvas:#ffffff;--soft:#f7f7f8;--bubble:#f1f3f5;--warn:#8a6a2f;}
html,body,[data-testid="stApp"],[data-testid="stAppViewContainer"]{background:var(--canvas);color:var(--ink)}
[data-testid="stToolbar"],[data-testid="stDeployButton"],#MainMenu,footer{display:none!important}
[data-testid="stHeader"]{background:transparent}
.block-container{max-width:860px;padding:0 28px 9rem!important}

/* ---------- barra lateral ---------- */
section[data-testid="stSidebar"]{width:290px!important;min-width:290px!important;background:var(--soft);
  border-right:1px solid var(--line)}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding:20px 16px}
.brand{display:flex;align-items:center;gap:11px;margin:2px 4px 18px}
.brand-mark{width:38px;height:38px;border-radius:12px;display:grid;place-items:center;color:#fff;font-size:20px;
  background:linear-gradient(135deg,var(--accent),#4b8dbb);box-shadow:0 8px 22px rgba(31,95,139,.25)}
.brand-name{font-size:1.12rem;font-weight:740;letter-spacing:-.02em;line-height:1.15}
.brand-tag{font-size:.74rem;color:var(--muted)}
section[data-testid="stSidebar"] .stButton button{justify-content:flex-start;text-align:left;border-radius:12px;
  border:1px solid transparent;background:transparent;color:var(--ink);font-weight:560;padding:.5rem .75rem}
section[data-testid="stSidebar"] .stButton button:hover{background:#ececee;border-color:transparent}
section[data-testid="stSidebar"] .stButton button[data-testid="stBaseButton-primary"]{background:var(--accent-soft);
  color:var(--accent-dark);border-color:#cfe0ee}
section[data-testid="stSidebar"] .st-key-new_chat button{border:1px solid var(--line);background:#fff;font-weight:650}
section[data-testid="stSidebar"] .st-key-new_chat button:hover{border-color:var(--accent);background:#fff}
.side-card{margin:14px 2px;padding:12px 13px;border:1px solid var(--line);border-radius:14px;background:#fff;
  font-size:.78rem;line-height:1.55;color:var(--muted)}
.side-card b{color:var(--ink)}
.side-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#34c38f;margin-right:7px;
  box-shadow:0 0 0 4px rgba(52,195,143,.15)}
.side-dot.off{background:#f5a524;box-shadow:0 0 0 4px rgba(245,165,36,.16)}
.side-note{font-size:.72rem;color:var(--muted);margin:10px 4px;line-height:1.5}

section[data-testid="stSidebar"] .stButton button>div,section[data-testid="stSidebar"] .stButton button [data-testid="stMarkdownContainer"]{
  justify-content:flex-start!important;text-align:left!important}
section[data-testid="stSidebar"] .stButton button{gap:.55rem}
.side-label{font-size:.7rem;font-weight:650;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:16px 6px 4px}
.attention{background:#fff8e8;border:1px solid #f0e0b8;border-radius:12px;padding:10px 14px;margin:8px 0 10px;
  font-size:.88rem;color:#5c4a1f}
.attention ul{margin:4px 0 0;padding-left:1.1rem}
/* ---------- cabeçalho fixo ---------- */
div[data-testid="stElementContainer"]:has(.app-header){position:sticky;top:0;z-index:50;
  background:rgba(255,255,255,.93);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.app-header{min-height:62px;display:flex;align-items:center;justify-content:space-between}
.app-title{font-weight:730;font-size:1.02rem;letter-spacing:-.015em}
.app-title span{color:var(--accent)}
.app-pill{font-size:.72rem;color:var(--muted);background:var(--bubble);padding:6px 11px;border-radius:999px}

/* ---------- boas-vindas ---------- */
.welcome{display:flex;flex-direction:column;align-items:center;text-align:center;padding:46px 0 14px}
.welcome-mark{width:56px;height:56px;border-radius:18px;display:grid;place-items:center;color:#fff;font-size:28px;
  background:linear-gradient(135deg,var(--accent),#4b8dbb);box-shadow:0 12px 30px rgba(31,95,139,.24)}
.welcome h1{font-size:2rem;margin:18px 0 6px;letter-spacing:-.035em}
.welcome p{color:var(--muted);margin:0;max-width:560px}
.st-key-suggestions [data-testid="stColumn"]{flex:1 1 0;min-width:0}
.st-key-suggestions .stButton button{width:100%;height:86px;text-align:left;justify-content:flex-start;
  border:1px solid var(--line);border-radius:16px;background:#fff;color:var(--ink);font-weight:520;
  line-height:1.4;padding:.7rem .95rem;box-shadow:0 1px 2px rgba(16,24,40,.03)}
.st-key-suggestions .stButton button p{white-space:normal;text-align:left;margin:0}
.st-key-suggestions .stButton button>div{justify-content:flex-start;text-align:left;width:100%}
.st-key-suggestions .stButton button:hover{border-color:var(--accent);background:var(--accent-soft)}

/* ---------- mensagens ---------- */
.user-row{width:100%;display:flex;justify-content:flex-end;margin:18px 0 8px}
.user-bubble{width:fit-content;max-width:78%;padding:10px 16px;background:var(--bubble);border-radius:20px;
  line-height:1.55;overflow-wrap:anywhere;white-space:pre-wrap}
[data-testid="stChatMessage"]{background:transparent;padding:6px 0;margin:6px 0}
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarAssistant"]{background:var(--accent);color:#fff}
[data-testid="stChatMessageContent"]{font-size:.96rem;line-height:1.68}
.meta{font-size:.72rem;color:var(--muted);margin:2px 0 6px}
.ctx{font-size:.8rem;color:var(--muted);line-height:1.6;margin:0;padding-left:1.1rem}
.notice{font-size:.78rem;color:var(--warn);background:#fff8e8;border:1px solid #f0e0b8;border-radius:10px;
  padding:7px 11px;margin:6px 0}
[data-testid="stSpinner"]{color:var(--accent)}

/* ---------- caixa de pergunta (fixa no rodapé) ---------- */
[data-testid="stBottom"]{background:linear-gradient(180deg,rgba(255,255,255,0),#fff 28%)}
[data-testid="stChatInput"]{border:1px solid #d5d9de;border-radius:26px;background:#fff;
  box-shadow:0 6px 26px rgba(16,24,40,.09)}
[data-testid="stChatInput"]:focus-within{border-color:var(--accent);box-shadow:0 6px 28px rgba(31,95,139,.16)}
[data-testid="stChatInputSubmitButton"]{background:var(--accent)!important;color:#fff!important;border-radius:50%!important}
[data-testid="stChatInputSubmitButton"] svg{color:#fff!important;fill:#fff!important;opacity:1!important}
[data-testid="stChatInputSubmitButton"]:hover{background:var(--accent-dark)!important}

/* ---------- tabelas, métricas e abas ---------- */
[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px 14px}
[data-testid="stMetricLabel"]{color:var(--muted)}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"]{color:var(--accent-dark)}
.view-title{font-size:1.5rem;font-weight:740;letter-spacing:-.025em;margin:20px 0 2px}
.view-sub{color:var(--muted);margin:0 0 14px;font-size:.92rem}
@media(max-width:760px){.block-container{padding:0 12px 9rem!important}.app-pill{display:none}
  .user-bubble{max-width:90%}.welcome{padding-top:26px}.welcome h1{font-size:1.65rem}}
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header(title_html: str, pill: str = "") -> None:
    st.markdown(f'<div class="app-header"><div class="app-title">{title_html}</div>'
                + (f'<div class="app-pill">{pill}</div>' if pill else "") + "</div>", unsafe_allow_html=True)


def view_title(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="view-title">{title}</div><p class="view-sub">{subtitle}</p>', unsafe_allow_html=True)
