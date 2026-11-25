"""Controles baratos antes do LLM. Complementam, mas não substituem, a validação do SQL."""
import re
import unicodedata

_VERBS = (r"ignor\w*|disregard\w*|forget\w*|bypass\w*|overrid\w*|jailbreak\w*|esque[cç]\w*|desconsider\w*|"
          r"contorn\w*|sobrescrev\w*|desobede\w*")
# "regras/sistema" sozinhos aparecem em perguntas de negócio ("regras de arredondamento"): só valem com qualificador
_OVERRIDE = re.compile(
    rf"\b(?:{_VERBS})\b.{{0,60}}\b(?:instructions?|prompts?|instru[cç][aã]o|instru[cç][oõ]es|"
    rf"(?:rules?|regras?|system|sistema)\s+(?:anteriores?|acima|previous|above|originais|original|internas?|internal|"
    rf"do sistema|of the system)|(?:your|suas?|seus?|its)\s+(?:rules?|regras?|system|sistema))",
    re.IGNORECASE | re.DOTALL,
)
_EXFILTRATE = re.compile(
    r"\b(reveal|show|print|repeat|expose|mostrar|revelar|imprimir|repetir|expor)\b.{0,80}"
    r"\b(system prompt|developer message|hidden instruction|prompt do sistema|mensagem do desenvolvedor|"
    r"instru[cç][oõ]es? (?:ocultas?|internas?))\b",
    re.IGNORECASE | re.DOTALL,
)
_ROLE_FORGERY = re.compile(r"(?:^|\n)\s*(system|developer|assistant|sistema|desenvolvedor)\s*:", re.IGNORECASE)


def inspect_question(question: str) -> str | None:
    """Retorna o motivo da recusa ou None. Analisa uma cópia normalizada do texto."""
    if not isinstance(question, str) or not question.strip():
        return "Escreva uma pergunta sobre os dados."
    normalized = unicodedata.normalize("NFKC", question)
    # Caracteres invisíveis incomuns podem transportar instruções sem aparecer na tela.
    if any(unicodedata.category(c) == "Cf" and c not in "\u200c\u200d" for c in normalized):
        return "A pergunta contém caracteres invisíveis não permitidos."
    if _OVERRIDE.search(normalized) or _EXFILTRATE.search(normalized) or _ROLE_FORGERY.search(normalized):
        return "Não posso alterar minhas instruções internas. Faça uma pergunta sobre produção, segurança ou meio ambiente."
    return None
