import re
import time

import requests
from . import config


MAX_WAIT_S = 25   # espera máxima por tentativa quando o provedor devolve 429 (limite por minuto)


def _post(url: str, what: str, **kw):
    """POST com até 2 novas tentativas em 429, respeitando o tempo sugerido pelo provedor."""
    for attempt in range(3):
        r = requests.post(url, **kw)
        if r.status_code != 429 or attempt == 2:
            _check(r, what)
            return r
        m = re.search(r"try again in ([0-9.]+)s", r.text) or re.search(r"retry-after.*?([0-9.]+)", str(getattr(r, "headers", "")), re.I)
        wait = min(float(m.group(1)) + 1 if m else 10, MAX_WAIT_S)
        time.sleep(wait)


def _check(r, what: str):
    """raise_for_status, mas com o corpo da resposta (traz o motivo real, ex.: modelo não encontrado)."""
    if r.status_code >= 400:
        raise RuntimeError(f"{what}: HTTP {r.status_code} — {r.text.strip()[:300]}")


class LLM:
    def chat(self, messages: list[dict]) -> str:
        raise NotImplementedError


class Ollama(LLM):
    def chat(self, messages):
        headers = {"Authorization": f"Bearer {config.OLLAMA_API_KEY}"} if config.OLLAMA_API_KEY else {}
        r = _post(f"{config.OLLAMA_URL}/api/chat", f"Ollama (modelo '{config.OLLAMA_MODEL}')", timeout=300, headers=headers, json={
            "model": config.OLLAMA_MODEL, "messages": messages, "stream": False,
            "options": {"temperature": 0}})
        return r.json()["message"]["content"]


class Groq(LLM):
    def chat(self, messages):
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY não configurada")
        r = _post(f"{config.GROQ_BASE_URL}/chat/completions", f"Groq (modelo '{config.GROQ_MODEL}')", timeout=120,
            headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
            json={"model": config.GROQ_MODEL, "messages": messages, "temperature": 0})
        return r.json()["choices"][0]["message"]["content"]


def get_llm() -> LLM:
    return {"ollama": Ollama, "groq": Groq}[config.LLM_PROVIDER]()
