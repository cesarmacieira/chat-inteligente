import sqlglot
from sqlglot import exp


class UnsafeSQL(ValueError):
    pass


def validate(sql: str, allowed_tables: set[str], max_rows: int) -> str:
    """Aceita só um SELECT sobre tabelas permitidas; força LIMIT."""
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
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if name not in allowed_tables and name not in ctes:
            raise UnsafeSQL(f"Tabela não permitida: {t.name}")
    for f in tree.find_all(exp.Anonymous):
        if f.name.lower().startswith(("read_", "glob", "pragma")):
            raise UnsafeSQL("Função não permitida.")
    return f"SELECT * FROM ({tree.sql(dialect='duckdb')}) AS _q LIMIT {max_rows}"
