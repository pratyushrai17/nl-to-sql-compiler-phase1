"""
repair_loop.py

Orchestrates the full pipeline for one question:

    generate SQL (LLM) -> tokenize -> parse -> semantic-validate
        -> on failure, send errors back to the LLM -> retry (bounded)

Phase 1 scope: a bounded, linear retry loop (no backoff, no sophisticated
prompt strategy) — see CLAUDE.md. `max_retries` caps the number of repair
attempts *after* the first one.

`seed_sql` is a deliberate Phase 1 demo hook: it lets main.py hand the loop
a hardcoded (intentionally invalid) first attempt instead of calling the LLM
for attempt #1, so the "validation fails, then gets repaired" path is
reliably demoable live instead of depending on the LLM happening to make a
mistake on that run. Every attempt *after* the first still goes through the
real LLM repair call. When seed_sql is omitted (the normal case), attempt #1
comes from the LLM like every other attempt.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from ast_nodes import SelectStatement
from lexer import LexError, tokenize
from llm_client import generate_sql
from parser import ParseError, parse
from semantic_analyzer import analyze
from symbol_table import schema_description


@dataclass
class Attempt:
    number: int
    sql: str
    source: str  # "llm" or "seed (simulated bad first attempt)"
    tokens: Optional[list] = None
    ast: Optional[SelectStatement] = None
    errors: List[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class PipelineResult:
    question: str
    attempts: List[Attempt]
    success: bool

    @property
    def final(self) -> Attempt:
        return self.attempts[-1]


def run_pipeline(question: str, max_retries: int = 2, seed_sql: str = None) -> PipelineResult:
    schema = schema_description()
    attempts: List[Attempt] = []

    sql = seed_sql
    source = "seed (simulated bad first attempt)" if seed_sql else "llm"

    for attempt_number in range(1, max_retries + 2):  # attempt 1 + up to max_retries repairs
        if sql is None:
            sql = generate_sql(question, schema)

        errors: List[str] = []
        tokens = None
        ast = None

        try:
            tokens = tokenize(sql)
        except LexError as e:
            errors.append(f"Lex error: {e}")

        if tokens is not None and not errors:
            try:
                ast = parse(tokens)
            except ParseError as e:
                errors.append(f"Parse error: {e}")

        if ast is not None and not errors:
            errors = analyze(ast)

        attempts.append(Attempt(
            number=attempt_number, sql=sql, source=source,
            tokens=tokens, ast=ast, errors=errors,
        ))

        if not errors:
            return PipelineResult(question=question, attempts=attempts, success=True)

        if attempt_number == max_retries + 1:
            return PipelineResult(question=question, attempts=attempts, success=False)

        sql = generate_sql(question, schema, previous_sql=sql, errors=errors)
        source = "llm (repair)"

    return PipelineResult(question=question, attempts=attempts, success=False)  # unreachable
