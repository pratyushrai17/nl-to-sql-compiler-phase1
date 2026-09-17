# NL -> SQL Compiler (Phase 1 Prototype)

A system that translates natural language questions into SQL, then validates
the generated SQL using hand-written compiler front-end techniques (lexer,
recursive-descent parser, AST, semantic analysis against a symbol table)
*before* running it — instead of trusting LLM output directly. On a
validation failure, the error is fed back to the LLM for a bounded number of
repair attempts.

**This is the Phase 1 / Review 1 deliverable**: an initial prototype
demonstrating the pipeline concept end-to-end on a few hardcoded examples.
It is intentionally minimal — a small grammar, basic error handling, a
2-retry repair loop — not a complete or robust system. Full core
implementation is Phase 2; full testing, error handling, and polish are
Phase 3. See `CLAUDE.md` for the full project context and constraints.

## Pipeline

```
NL question
  -> LLM generates candidate SQL              (llm_client.py)
  -> hand-written lexer tokenizes it           (lexer.py)
  -> hand-written parser builds an AST         (parser.py, ast_nodes.py)
  -> semantic analyzer validates the AST       (semantic_analyzer.py)
     against a fixed schema                    (symbol_table.py)
  -> on error: error text -> LLM -> retry       (repair_loop.py, bounded)
  -> once valid: run against SQLite            (db.py)
  -> print every stage                         (main.py)
```

**Hard constraint:** the lexer, parser, AST, symbol table, and semantic
analyzer are all hand-written from scratch. No `sqlparse`, `sqlglot`, ANTLR,
or any other SQL parsing library is used anywhere in this project.

## Schema (Library database)

| Table   | Columns                          |
|---------|-----------------------------------|
| Books   | id, title, author, genre          |
| Members | id, name, joined_on               |
| Loans   | id, book_id, member_id, due_date  |

Hardcoded in `symbol_table.py`; `db.py` seeds an in-memory SQLite database
with a handful of sample rows for each table.

## Grammar supported (Phase 1 subset)

`SELECT` only: a select list of columns / `*` / aggregate calls
(`COUNT`/`SUM`/`AVG`/`MIN`/`MAX`), one `FROM` table, optional `JOIN ... ON`,
optional `WHERE` with `AND`/`OR`, optional `GROUP BY`, optional `ORDER BY`
with `ASC`/`DESC`. No subqueries, no parenthesized boolean expressions, no
`HAVING`, no INSERT/UPDATE/DELETE/DDL — see `parser.py`'s module docstring
for the exact grammar.

## Setup

```bash
pip install -r requirements.txt
```

Set your Anthropic API key (the LLM step needs it):

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # macOS/Linux
setx ANTHROPIC_API_KEY "sk-ant-..."        # Windows (new shells)
```

**No API key? `main.py` still runs.** If `ANTHROPIC_API_KEY` isn't set,
`llm_client.py` automatically falls back to a stub that returns pre-written
SQL for the three built-in demo questions (`STUB_RESPONSES` in
`llm_client.py`) instead of calling the API — including a deliberately
invalid first response for example 3, so the repair path still runs with no
live model involved. A `[llm_client] ... running in STUB MODE` note prints
once so it's never mistaken for real LLM output. Stub mode only covers the
built-in demo questions; anything else raises a clear error asking for a
real key.

## Running

**Full pipeline demo** (uses the real LLM if `ANTHROPIC_API_KEY` is set,
otherwise runs in stub mode automatically — see above):

```bash
python main.py
```

Runs the three hardcoded examples from `tests/examples.py` through the full
pipeline and prints every stage: tokens, AST, validation result, retries (if
any), the final validated SQL, and the query results from SQLite.

**Offline sanity checks** for the hand-written lexer/parser/semantic
analyzer — no API key needed:

```bash
python -m tests.test_pipeline
```

## The three demo examples

1. *"List the titles and authors of every Dystopian book."* — a plain
   `WHERE` query. Expected to pass validation on the LLM's first attempt.
2. *"How many books are there in each genre?"* — a `GROUP BY` + `COUNT(*)`
   query. Also expected to pass on the first attempt.
3. *"For each genre, show the author and how many books there are."* —
   deliberately seeded with an invalid first attempt
   (`SELECT genre, author, COUNT(*) FROM Books GROUP BY genre`) that trips
   the aggregate/`GROUP BY` misuse check: `author` is selected alongside
   `COUNT(*)` but is neither aggregated nor grouped. The error is fed back
   to the LLM, which repairs it on the next attempt — demonstrating the
   validate-and-repair loop live.

Example 3's *first* attempt is hardcoded (see `repair_loop.run_pipeline`'s
`seed_sql` parameter) rather than left to the LLM, so the failure-then-repair
path is reliably demoable in a live review instead of depending on the LLM
happening to make that exact mistake on the day. The *repair* itself is
still a genuine LLM call, driven by the real semantic-analyzer error
message — nothing about the repair is scripted.

## Module map

| File                   | Responsibility                                       |
|------------------------|-------------------------------------------------------|
| `lexer.py`              | Tokenizer for the supported SQL subset                |
| `parser.py`             | Recursive-descent parser -> AST                       |
| `ast_nodes.py`          | AST node definitions (dataclasses)                    |
| `symbol_table.py`       | Hardcoded schema + lookup helpers                     |
| `semantic_analyzer.py`  | Validates an AST against the schema                   |
| `llm_client.py`         | Wraps the Anthropic API for SQL generation/repair      |
| `repair_loop.py`        | Orchestrates generate -> validate -> retry             |
| `db.py`                 | In-memory SQLite + sample data                        |
| `main.py`               | CLI entry point; runs and prints the full demo         |
| `tests/examples.py`     | The 2-3 example questions used by `main.py`            |
| `tests/test_pipeline.py`| Offline checks for lexer/parser/semantic analyzer      |

## Known Phase 1 limitations

These are deliberate scope cuts, not oversights — see CLAUDE.md's Phase
status section. They're addressed in Phase 2/3:

- Small grammar (no subqueries, no parenthesized WHERE expressions, no
  `HAVING`).
- Semantic analyzer implements one aggregate/GROUP BY check and
  undefined/ambiguous table & column detection — not a full set of SQL
  semantic rules.
- Repair loop is a flat bounded retry (2 attempts) with no smarter retry
  strategy.
- Minimal error handling elsewhere; not hardened against malformed input.
