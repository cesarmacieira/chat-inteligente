import tempfile
from pathlib import Path
import pytest
from chat_inteligente import config, synth, run_daily


@pytest.fixture(scope="session", autouse=True)
def warehouse():
    # não usa o tmp_path do pytest (a pasta pytest-of-<user> pode estar sem permissão)
    config.DB_PATH = Path(tempfile.mkdtemp(prefix="chat_inteligente_")) / "t.duckdb"
    config.HISTORY_PATH = config.DB_PATH.parent / "hist.sqlite"
    synth.generate(end="2026-11-09")   # data fixa: testes determinísticos
    run_daily.main()
