import re
import time
import unicodedata
from dataclasses import dataclass, field
import pandas as pd
import yaml
from . import config, context, labels
from .db import connect
from .llm import LLM, get_llm
from .sql_guard import UnsafeSQL, validate


@dataclass
class Answer:
    sql: str
    df: pd.DataFrame | None
    text: str
    error: str | None = None
    context: list[str] = field(default_factory=list)
    attention: list[str] = field(default_factory=list)   # pontos de atenção em linguagem de negócio
    attempts: list[dict] = field(default_factory=list)   # cada SQL tentado: {sql, ok, error}
    secs: float = 0.0


def load_catalog() -> dict:
    return yaml.safe_load(config.CATALOG_PATH.read_text(encoding="utf-8"))


def _tokens(text: str) -> set[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z_]{4,}", t)}


def pick_examples(cat: dict, question: str | None, k: int = 4) -> list[dict]:
    """Os k exemplos mais parecidos com a pergunta (poupa tokens em LLMs com limite por minuto)."""
    exs = cat["examples"]
    if question is None or len(exs) <= k:
        return exs
    qt = _tokens(question)
    scored = sorted(range(len(exs)), key=lambda i: (-len(qt & _tokens(exs[i]["q"] + " " + exs[i]["sql"])), i))
    return [exs[i] for i in scored[:k]]


def catalog_prompt(cat: dict, question: str | None = None, k: int = 4) -> str:
    lines = [cat["notes"], "TABELAS:"]
    for t, d in cat["tables"].items():
        lines.append(f"- {t}: {d['description']}")
        lines += [f"    {c}: {desc}" for c, desc in d["columns"].items()]
    lines.append("EXEMPLOS:")
    for ex in pick_examples(cat, question, k):
        lines.append(f"P: {ex['q']}\nSQL:\n{ex['sql']}")
    return "\n".join(lines)


def live_context() -> str:
    """Entidades e métricas realmente presentes no banco (evita o LLM inventar ids)."""
    try:
        con = connect(read_only=True)
        try:
            ents = con.execute("SELECT entity_id, name, planta, tipo FROM entities ORDER BY 1").fetchall()
            mets = con.execute("SELECT metric, area, unidade, agregacao FROM metrics_catalog ORDER BY 2, 1").fetchall()
            hoje = con.execute("SELECT MIN(ref_date), MAX(ref_date) FROM daily_metrics").fetchone()
        finally:
            con.close()
    except Exception:
        return ""
    lines = [f"DADOS DISPONÍVEIS (de {hoje[0]} a {hoje[1]}):", "Entidades (entity_id | nome | planta | tipo):"]
    lines += [f"  {a} | {b} | {c} | {d}" for a, b, c, d in ents]
    lines.append("Métricas (metric | área | unidade | agregação):")
    lines += [f"  {a} | {b} | {c} | {d}" for a, b, c, d in mets]
    return "\n".join(lines)


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip().rstrip(";")


SUMMARY_PROMPT = (
    "Você escreve para a DIRETORIA de uma siderúrgica (os dados são fictícios). Português do Brasil, tom executivo, "
    "direto e sem jargão técnico: nunca cite nomes de colunas, SQL, tabelas, 'score', 'outlier', 'p-valor' ou ids de "
    "métricas (use o nome do indicador, ex.: 'produção', 'taxa de rejeição'). Use SOMENTE os números do resultado e do "
    "contexto; nunca invente valores nem percentuais.\n"
    "Formato: comece com UMA frase que responde à pergunta, citando o NOME de cada ativo/área, a data ou período e os "
    "valores com unidade (ex.: 1.203 t), milhar em ponto e decimal em vírgula. Depois, no máximo 3 marcadores curtos "
    "(com '- ', sem numeração) com o que importa: maior e menor, diferença entre eles, posição no ranking. Se o "
    "CONTEXTO trouxer tendência, valor fora do padrão ou limite, feche com UMA frase de atenção em linguagem de negócio.\n"
    "Regras: o resultado TEM linhas e responde à pergunta, nunca diga que não há informação. Só some valores se a "
    "pergunta pedir total e a agregação da métrica for 'soma' (nunca some médias, taxas ou concentrações). "
    "Só calcule variação percentual se os dois valores estiverem no resultado. Para valor esperado, diga 'acima/abaixo "
    "do esperado' e a diferença. Em série longa, destaque início, fim, maior e menor.")


class Agent:
    def __init__(self, llm: LLM | None = None):
        self.llm = llm or get_llm()
        self.cat = load_catalog()
        self.allowed = {t.lower() for t in self.cat["tables"]}
        self.head = ("Você converte perguntas em UMA consulta SQL (DuckDB) somente de leitura. "
                     "Responda apenas com o SQL em um bloco ```sql.\n\n")
        self.system = ""

    def _run(self, sql: str) -> tuple[pd.DataFrame, str]:
        safe = validate(sql, self.allowed, config.MAX_ROWS)
        con = connect(read_only=True)
        try:
            return con.execute(safe).df(), safe
        finally:
            con.close()

    def ask(self, question: str, history: list[dict] | None = None) -> Answer:
        t0 = time.time()
        ans = self._ask(question, history)
        ans.secs = time.time() - t0
        return ans

    def _ask(self, question: str, history: list[dict] | None = None) -> Answer:
        self.system = self.head + catalog_prompt(self.cat, question) + "\n\n" + live_context()
        msgs = [{"role": "system", "content": self.system}, *(history or []),
                {"role": "user", "content": question}]
        sql, err, attempts = "", None, []
        for _ in range(2):  # 1 tentativa + 1 correção
            sql = extract_sql(self.llm.chat(msgs))
            try:
                df, safe = self._run(sql)
                attempts.append({"sql": sql, "ok": True, "error": None, "executed": safe})
                break
            except (UnsafeSQL, Exception) as e:
                err = str(e)
                attempts.append({"sql": sql, "ok": False, "error": err})
                msgs += [{"role": "assistant", "content": f"```sql\n{sql}\n```"},
                         {"role": "user", "content": f"Erro: {err}. Corrija o SQL."}]
        else:
            return Answer(sql, None, "Não consegui montar uma consulta válida para essa pergunta. "
                          "Tente reformular, citando o ativo, o indicador e o período.", err, attempts=attempts)
        if df.empty:
            msg = "A consulta rodou, mas não retornou nenhuma linha para esse filtro."
            if "v_outliers" in sql.lower():
                msg += (" Os modelos só registram os dias fora do padrão; se o filtro era um dia específico, "
                        "isso indica que ele não foi sinalizado como outlier. Tente perguntar pelo valor do dia.")
            return Answer(sql, df, msg, attempts=attempts)
        ctx = context.build(sql, df)
        att = context.build(sql, df, friendly=True)
        cols = ", ".join(f"{c} ({t})" for c, t in zip(df.columns, df.dtypes.astype(str)))
        summary = self.llm.chat([
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": f"Pergunta: {question}\nColunas: {cols}\n"
                                        f"Resultado ({len(df)} linhas; até 30 mostradas):\n{df.head(30).to_csv(index=False)}"
                                        + ("\nCONTEXTO (métricas e modelos de ML):\n" + "\n".join(f"- {l}" for l in ctx) if ctx else "")}])
        return Answer(sql, df, labels.clean_text(summary), context=ctx, attention=att, attempts=attempts)
