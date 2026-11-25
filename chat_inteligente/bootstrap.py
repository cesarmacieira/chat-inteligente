"""Prepara o banco na primeira execução (ex.: Streamlit Cloud, cujo disco é efêmero).

Ligado por padrão (AUTO_BOOTSTRAP=0 desliga); age apenas quando o banco está ausente, vazio ou sem execução dos modelos.
Em ambiente local, com dados reais, nunca sobrescreve nada.
"""
import logging
from datetime import date

import duckdb

from . import config, overview, run_daily, synth

logger = logging.getLogger(__name__)


def db_kind() -> str:
    """Classifica o arquivo do banco: 'missing' | 'empty' | 'synthetic' | 'real' | 'unknown'.
    Só 'missing', 'empty' e 'synthetic' podem ser (re)gerados; 'real' e 'unknown' (travado, corrompido, erro de
    leitura) nunca são tocados."""
    if not config.DB_PATH.exists():
        return "missing"
    try:
        con = duckdb.connect(str(config.DB_PATH), read_only=True)
    except Exception:
        return "unknown"
    try:
        tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        if "app_meta" in tables:
            r = con.execute("SELECT value FROM app_meta WHERE key = 'source'").fetchall()
            if r and str(r[0][0]).startswith("sint"):
                return "synthetic"
        # Um arquivo sem nenhuma tabela é descartável. Qualquer tabela sem marcador sintético pode ser dado real
        # ainda não carregado, staging ou legado e jamais deve ser substituída pela demonstração.
        if not tables:
            return "empty"
        return "real"
    except Exception:
        return "unknown"
    finally:
        con.close()


def ensure_data() -> bool:
    """Retorna True se preparou dados ou modelos nesta chamada."""
    if not config.AUTO_BOOTSTRAP:
        return False
    st = overview.status()
    if st.get("ok"):
        synthetic = str(st.get("source") or "").startswith("sint")
        data_fresh = not synthetic or st["date_max"] >= date.today().isoformat()
        models_fresh = (st.get("has_run") and not st.get("stale")
                        and st.get("model_version") == run_daily.MODEL_VERSION
                        and st.get("has_forecasts"))
        if data_fresh and models_fresh:
            return False
        # Dados reais nunca são sobrescritos: apenas migra o schema e recalcula os modelos.
        if synthetic and not data_fresh:
            synth.generate()
        run_daily.main()
        return True
    kind = db_kind()
    if kind not in ("missing", "empty", "synthetic"):
        logger.warning("Banco %s (%s) não está no formato esperado e contém dados que não são da demonstração: "
                       "nada foi alterado. Migre manualmente (python -m chat_inteligente.run_daily) ou use outro DB_PATH.",
                       config.DB_PATH, kind)
        return False
    synth.generate()
    run_daily.main()
    return True
