"""
main.py

CLI entry point and the live-demo script for Review 1. Runs the hardcoded
example questions in tests/examples.py through the full pipeline and prints
every stage: tokens, AST, validation result (including retries), final SQL,
and query results.

Requires ANTHROPIC_API_KEY to be set (the LLM generates and repairs SQL).

Run with:  python main.py
"""

import dataclasses
import sys

from db import get_connection, run_query
from llm_client import LLMError
from repair_loop import run_pipeline
from tests.examples import EXAMPLES

BAR = "=" * 78


def section(title):
    print(f"\n{BAR}\n{title}\n{BAR}")


def format_ast(node, indent=0):
    """Small recursive pretty-printer for AST nodes, for demo readability.
    Leans on each node's custom __repr__ (ast_nodes.py) for leaf values."""
    pad = "  " * indent
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        lines = [f"{pad}{type(node).__name__}"]
        for f in dataclasses.fields(node):
            value = getattr(node, f.name)
            if isinstance(value, list):
                if not value:
                    lines.append(f"{pad}  {f.name}: []")
                else:
                    lines.append(f"{pad}  {f.name}:")
                    for item in value:
                        lines.append(format_ast(item, indent + 2))
            elif dataclasses.is_dataclass(value):
                lines.append(f"{pad}  {f.name}:")
                lines.append(format_ast(value, indent + 2))
            else:
                lines.append(f"{pad}  {f.name}: {value}")
        return "\n".join(lines)
    return f"{pad}{node}"


def print_tokens(tokens):
    if tokens is None:
        print("  (tokenization failed before any tokens were produced)")
        return
    shown = [t for t in tokens if t.type != "EOF"]
    print("  " + "  ".join(f"[{t.type}:{t.value}]" for t in shown))


def print_attempt(attempt):
    print(f"\n--- Attempt {attempt.number} (SQL source: {attempt.source}) ---")
    print(f"SQL: {attempt.sql}")

    print("\nTokens:")
    print_tokens(attempt.tokens)

    print("\nAST:")
    if attempt.ast is not None:
        print(format_ast(attempt.ast, indent=1))
    else:
        print("  (no AST - parsing did not succeed)")

    print("\nValidation:")
    if attempt.valid:
        print("  VALID")
    else:
        for err in attempt.errors:
            print(f"  ERROR: {err}")


def print_results(columns, rows):
    if not rows:
        print("  (no rows returned)")
        return
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(columns)]
    header = "  " + " | ".join(c.ljust(w) for c, w in zip(columns, widths))
    print(header)
    print("  " + "-+-".join("-" * w for w in widths))
    for row in rows:
        print("  " + " | ".join(str(v).ljust(w) for v, w in zip(row, widths)))


def run_example(conn, example, index):
    section(f"Example {index}: {example['question']}")

    try:
        result = run_pipeline(
            question=example["question"],
            max_retries=2,
            seed_sql=example.get("seed_sql"),
        )
    except LLMError as e:
        print(f"\nLLM call failed: {e}")
        print("Set ANTHROPIC_API_KEY and try again.")
        return False

    for attempt in result.attempts:
        print_attempt(attempt)

    print(f"\n--- Result: {'SUCCESS' if result.success else 'FAILED'} "
          f"after {len(result.attempts)} attempt(s) ---")

    if not result.success:
        return False

    final_sql = result.final.sql
    print(f"\nFinal validated SQL:\n  {final_sql}")

    print("\nQuery results:")
    columns, rows = run_query(conn, final_sql)
    print_results(columns, rows)
    return True


def main():
    print("NL -> SQL compiler pipeline - Phase 1 prototype demo")
    print(f"Running {len(EXAMPLES)} hardcoded example(s).")

    conn = get_connection()
    outcomes = []
    for i, example in enumerate(EXAMPLES, start=1):
        outcomes.append(run_example(conn, example, i))
    conn.close()

    section("Summary")
    for example, ok in zip(EXAMPLES, outcomes):
        status = "OK" if ok else "FAILED"
        print(f"  [{status}] {example['question']}")

    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
