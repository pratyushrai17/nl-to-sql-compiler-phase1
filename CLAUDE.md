# CLAUDE.md

Project-wide context for the NL→SQL compiler project ("project2").
This file is loaded automatically in every session, including future phases.

## Project Overview

This project builds a system that translates natural language questions into SQL,
and validates the generated SQL using classical compiler front-end techniques
(lexing, parsing, AST construction, semantic analysis) before execution — rather
than trusting LLM output directly.

**Pipeline:**

```
NL question
  → LLM generates candidate SQL
  → hand-written lexer tokenizes it
  → hand-written recursive-descent parser builds an AST
  → semantic analyzer validates the AST against a fixed schema (symbol table)
  → on error, the error is fed back to the LLM to regenerate (bounded retries)
  → once valid, the query runs against SQLite and results are shown
```

This is a **compiler design course project**. The compiler front-end is the point
of the project; the LLM is just the front-end's input source.

## HARD CONSTRAINT (all phases)

The lexer, parser, AST, symbol table, and semantic analyzer **must all be
hand-written from scratch**.

Do **NOT** use `sqlparse`, `sqlglot`, ANTLR, PLY, Lark, or any other existing SQL
parsing / parser-generator library anywhere in this project. Doing so defeats the
purpose of a compiler design project and is not acceptable for grading.

The only third-party dependency permitted is the `anthropic` SDK (for the LLM
call). Everything else uses the Python standard library (`sqlite3`, etc.).

## Fixed Sample Schema — Library database

| Table   | Columns                                  |
|---------|------------------------------------------|
| Books   | id, title, author, genre                 |
| Members | id, name, joined_on                      |
| Loans   | id, book_id, member_id, due_date         |

The schema is fixed and hardcoded in `symbol_table.py`. It is the single source
of truth for semantic validation and for the schema description sent to the LLM.

## Scope

**In scope (across all phases):** `SELECT` statements only — `WHERE`, `JOIN`,
`GROUP BY`, `ORDER BY`, and aggregates (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`).

**Out of scope entirely:** `INSERT`, `UPDATE`, `DELETE`, and all DDL.

## Phase Status

This project has 3 phases:

- **Phase 1 (CURRENT)** — Review 1: Problem Definition and System Design.
  Minimal working prototype only. Demonstrates the pipeline concept end-to-end on
  a couple of hardcoded examples. Deliberately *not* robust: no extensive error
  handling, no exhaustive grammar, no polished retry system. Just enough SQL
  support to demo one or two working queries plus one that fails validation and
  gets repaired. **Prioritize runnable and demoable over complete.**
- **Phase 2** — Full core implementation of all modules.
- **Phase 3** — Complete integration, full testing, error handling, final polish.

When working in this repo, check which phase is current before expanding scope.
Do not build Phase 2/3 robustness during Phase 1.

## Project Structure

| File                   | Responsibility                                            |
|------------------------|-----------------------------------------------------------|
| `lexer.py`             | Tokenizer — SQL source text → token stream                |
| `parser.py`            | Recursive-descent parser — tokens → AST                   |
| `ast_nodes.py`         | AST node class definitions                                |
| `symbol_table.py`      | Hardcoded schema (tables / columns / types)               |
| `semantic_analyzer.py` | Validates AST against the symbol table                    |
| `llm_client.py`        | Wraps Anthropic API calls for SQL generation              |
| `repair_loop.py`       | Orchestrates generate → parse → validate → retry          |
| `db.py`                | In-memory SQLite setup with sample data                   |
| `main.py`              | CLI entry point; prints every pipeline stage clearly      |
| `tests/`               | Example queries used for demonstration                    |
| `README.md`            | How to run it, what each module does                      |

## Tech Details

- **Language:** Python (standard library only, plus the `anthropic` SDK).
- **LLM:** Anthropic API, model `claude-sonnet-5`, via the official `anthropic`
  Python SDK.
- **API key:** read from the `ANTHROPIC_API_KEY` environment variable. Never hardcode
  a key, and never commit one.
- **Database:** in-memory SQLite (`sqlite3`), seeded with sample rows at startup.

## Academic Integrity

This is an **individual academic project**. All code must be written for this
project — no copied or downloaded implementations of lexers, parsers, or analyzers.

## Working Conventions

- Keep modules single-purpose and importable in isolation — each stage of the
  pipeline should be testable on its own.
- `main.py` must print each pipeline stage visibly (tokens, AST, validation
  result, final SQL, query results). This output *is* the live demo.
- Prefer clear, readable code over clever code; this is read by a grader.
