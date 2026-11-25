import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _int_env(name: str, default: int, low: int, high: int) -> int:
    """Lê inteiro de ambiente sem impedir a inicialização por configuração inválida."""
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(low, min(value, high))

DB_PATH = Path(os.getenv("DB_PATH", "data/warehouse.duckdb"))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
MAX_ROWS = _int_env("MAX_ROWS", 200, 1, 10_000)
QUERY_TIMEOUT = _int_env("QUERY_TIMEOUT", 20, 1, 300)          # segundos por consulta gerada pelo LLM
QUERY_MEMORY_MB = _int_env("QUERY_MEMORY_MB", 1024, 128, 16384)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()   # groq | ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")              # só para Ollama Cloud (OLLAMA_URL=https://ollama.com)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
CATALOG_PATH = ROOT / "chat_inteligente" / "catalog.yaml"

# --- implantação ---
AUTO_BOOTSTRAP = os.getenv("AUTO_BOOTSTRAP", "1") == "1"      # padrão ligado: gera dados sintéticos + modelos só se o banco não existir (AUTO_BOOTSTRAP=0 desliga)

# --- histórico de conversas (auditoria: pergunta, resposta e o que foi executado) ---
HISTORY_PATH = Path(os.getenv("HISTORY_PATH", "data/chat_history.sqlite"))
if not HISTORY_PATH.is_absolute():
    HISTORY_PATH = ROOT / HISTORY_PATH
SHOW_TECHNICAL = os.getenv("SHOW_TECHNICAL", "1") == "1"       # mostra o expansor "Como chegamos a esse resultado"
