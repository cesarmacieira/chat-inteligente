import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("DB_PATH", "data/warehouse.duckdb"))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()   # groq | ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")              # só para Ollama Cloud (OLLAMA_URL=https://ollama.com)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
CATALOG_PATH = ROOT / "chat_inteligente" / "catalog.yaml"

# --- implantação (Streamlit Community Cloud) ---
APP_PASSWORD = os.getenv("APP_PASSWORD", "")                  # se definida, o app pede senha
MAX_QUESTIONS = int(os.getenv("MAX_QUESTIONS", "50"))         # perguntas por sessão (0 = sem limite); protege o custo da OpenAI
AUTO_BOOTSTRAP = os.getenv("AUTO_BOOTSTRAP", "0") == "1"      # gera dados sintéticos + modelos se o banco não existir

# --- histórico de conversas (auditoria: pergunta, resposta e o que foi executado) ---
HISTORY_PATH = Path(os.getenv("HISTORY_PATH", "data/chat_history.sqlite"))
if not HISTORY_PATH.is_absolute():
    HISTORY_PATH = ROOT / HISTORY_PATH
SHOW_TECHNICAL = os.getenv("SHOW_TECHNICAL", "1") == "1"       # mostra o expansor "Como chegamos a esse resultado"
