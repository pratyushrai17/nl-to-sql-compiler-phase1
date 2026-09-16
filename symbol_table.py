"""
symbol_table.py

The fixed schema for the Library database, used as the single source of truth
for semantic validation (semantic_analyzer.py) and for describing the schema
to the LLM (llm_client.py).

Phase 1 note: the schema is small and hardcoded on purpose. Nothing here reads
from a real database catalog — that's out of scope for a Review 1 prototype.
"""

# table_name -> {column_name: sql_type}
SCHEMA = {
    "Books": {
        "id": "INTEGER",
        "title": "TEXT",
        "author": "TEXT",
        "genre": "TEXT",
    },
    "Members": {
        "id": "INTEGER",
        "name": "TEXT",
        "joined_on": "TEXT",
    },
    "Loans": {
        "id": "INTEGER",
        "book_id": "INTEGER",
        "member_id": "INTEGER",
        "due_date": "TEXT",
    },
}

# Aggregate functions the semantic analyzer and parser both need to recognize.
AGGREGATE_FUNCTIONS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}


def table_exists(table_name: str) -> bool:
    return table_name in SCHEMA


def column_exists(table_name: str, column_name: str) -> bool:
    return table_exists(table_name) and column_name in SCHEMA[table_name]


def get_columns(table_name: str):
    return list(SCHEMA.get(table_name, {}).keys())


def schema_description() -> str:
    """Human-readable schema description, fed into the LLM prompt so it
    generates SQL against the real column names instead of guessing."""
    lines = []
    for table, columns in SCHEMA.items():
        col_list = ", ".join(f"{name} ({sql_type})" for name, sql_type in columns.items())
        lines.append(f"- {table}({col_list})")
    return "\n".join(lines)
