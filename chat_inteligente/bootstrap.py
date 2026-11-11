"""Prepara o banco na primeira execução (ex.: Streamlit Cloud, cujo disco é efêmero).

Só age com AUTO_BOOTSTRAP=1 e apenas quando o banco está ausente, vazio ou sem execução dos modelos.
Em ambiente local, com dados reais, nunca sobrescreve nada.
"""
from . import config, overview, run_daily, synth


def ensure_data() -> bool:
    """Retorna True se gerou os dados nesta chamada."""
    if not config.AUTO_BOOTSTRAP:
        return False
    st = overview.status()
    if st.get("ok") and st.get("has_run"):
        return False
    synth.generate()
    run_daily.main()
    return True
