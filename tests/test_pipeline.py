"""
tests/test_pipeline.py

Lightweight sanity checks for the hand-written lexer, parser, and semantic
analyzer — independent of the LLM, so this needs no ANTHROPIC_API_KEY.

Not a full test suite: Phase 1 scope is "a couple of hardcoded examples
that visibly work" (see CLAUDE.md), not exhaustive coverage — that's
Phase 2/3. Uses plain asserts + a __main__ runner rather than pytest, to
keep the only third-party dependency the `anthropic` SDK.

Run with:  python -m tests.test_pipeline
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lexer import tokenize  # noqa: E402
from parser import parse  # noqa: E402
from semantic_analyzer import analyze  # noqa: E402


def check(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    return condition


def test_lexer_basic():
    tokens = tokenize("SELECT title FROM Books WHERE genre = 'Fantasy'")
    types = [t.type for t in tokens]
    return check(
        "lexer: tokenizes a simple SELECT ... WHERE",
        types == ["SELECT", "IDENT", "FROM", "IDENT", "WHERE", "IDENT", "EQ", "STRING", "EOF"],
    )


def test_parser_valid_query():
    ast = parse(tokenize("SELECT title, author FROM Books WHERE genre = 'Fantasy'"))
    return check(
        "parser: builds a SelectStatement with 2 select items and a WHERE clause",
        len(ast.select_items) == 2 and ast.where is not None,
    )


def test_semantic_valid_query():
    ast = parse(tokenize("SELECT title, author FROM Books WHERE genre = 'Fantasy'"))
    return check("semantic: a valid query produces no errors", analyze(ast) == [])


def test_semantic_undefined_table():
    ast = parse(tokenize("SELECT * FROM NotATable"))
    errors = analyze(ast)
    return check(
        "semantic: an undefined table is caught",
        any("not defined in the schema" in e for e in errors),
    )


def test_semantic_undefined_column():
    ast = parse(tokenize("SELECT email FROM Members"))
    errors = analyze(ast)
    return check(
        "semantic: an undefined column is caught",
        any("does not exist" in e for e in errors),
    )


def test_semantic_group_by_misuse():
    ast = parse(tokenize("SELECT genre, author, COUNT(*) FROM Books GROUP BY genre"))
    errors = analyze(ast)
    return check(
        "semantic: aggregate/GROUP BY misuse is caught",
        any("GROUP BY" in e for e in errors),
    )


def test_semantic_group_by_correct():
    ast = parse(tokenize("SELECT genre, COUNT(*) FROM Books GROUP BY genre"))
    return check("semantic: a correct GROUP BY query produces no errors", analyze(ast) == [])


if __name__ == "__main__":
    results = [
        test_lexer_basic(),
        test_parser_valid_query(),
        test_semantic_valid_query(),
        test_semantic_undefined_table(),
        test_semantic_undefined_column(),
        test_semantic_group_by_misuse(),
        test_semantic_group_by_correct(),
    ]
    passed, total = sum(results), len(results)
    print(f"\n{passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)
