import sqlglot
from sqlglot import exp


class UnsafeSQL(ValueError):
    pass


def validate(sql: str, allowed_tables: set[str], max_rows: int) -> str:
    """Aceita só um SELECT sobre tabelas permitidas; força LIMIT."""
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 20_000:
        raise UnsafeSQL("Consulta vazia ou excessivamente longa.")
    if not isinstance(max_rows, int) or max_rows < 1 or max_rows > 10_000:
        raise UnsafeSQL("Limite de linhas inválido.")
    try:
        stmts = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQL(f"SQL inválido: {e}")
    if len(stmts) != 1 or stmts[0] is None:
        raise UnsafeSQL("Apenas uma instrução é permitida.")
    tree = stmts[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.With)) and not tree.find(exp.Select):
        raise UnsafeSQL("Apenas SELECT é permitido.")
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
                 exp.Alter, exp.Command, exp.Copy, exp.Attach)
    if any(tree.find(f) for f in forbidden):
        raise UnsafeSQL("Comando não permitido.")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    if any(w.args.get("recursive") for w in tree.find_all(exp.With)):
        raise UnsafeSQL("CTE recursiva não é permitida.")
    if len(list(tree.find_all(exp.CTE))) > 8 or len(list(tree.find_all(exp.Subquery))) > 12:
        raise UnsafeSQL("Consulta complexa demais.")
    joins = list(tree.find_all(exp.Join))
    if len(joins) > 5 or any(str(j.args.get("kind") or "").upper() == "CROSS" for j in joins):
        raise UnsafeSQL("Junção não permitida ou consulta complexa demais.")
    if any(not j.args.get("on") and not j.args.get("using") for j in joins):
        raise UnsafeSQL("Junção sem condição não é permitida.")
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if name not in allowed_tables and name not in ctes:
            raise UnsafeSQL(f"Tabela não permitida: {t.name}")
    blocked_functions = {
        "query", "query_table", "getenv", "current_setting", "sqlite_scan", "postgres_scan",
        "parquet_scan", "iceberg_scan", "delta_scan", "arrow_scan", "read_parquet", "read_json",
        "read_json_auto", "read_csv", "read_csv_auto", "read_text", "read_blob",
    }
    for f in tree.find_all(exp.Func):
        candidates = {str(getattr(f, "name", "")).lower()}
        try:
            candidates.add(str(f.sql_name()).lower())
        except (AttributeError, TypeError):
            pass
        if any(name in blocked_functions or name.startswith(
                ("read_", "glob", "pragma", "http", "sqlite_", "postgres_", "parquet_", "iceberg_", "delta_", "arrow_"))
               for name in candidates if name):
            raise UnsafeSQL("Função não permitida.")
    return f"SELECT * FROM ({tree.sql(dialect='duckdb')}) AS _q LIMIT {max_rows}"
