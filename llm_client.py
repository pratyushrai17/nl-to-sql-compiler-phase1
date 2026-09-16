"""
llm_client.py

Thin wrapper around the Anthropic API: turns a natural language question
into a candidate SQL query. repair_loop.py also uses this to ask for a fix,
by passing the previous invalid SQL plus the semantic/syntax errors.

Reads credentials the normal way the Anthropic SDK does (ANTHROPIC_API_KEY
env var, or another resolvable credential source) — no key handling of our
own.
"""

import re

from anthropic import (
    Anthropic,
    AuthenticationError,
    RateLimitError,
    APIStatusError,
    APIConnectionError,
)

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a SQL generator for a fixed SQLite schema. Given a natural \
language question, output exactly one SELECT statement that answers it, and nothing else.

Rules:
- Only use the tables and columns given in the schema below. Never invent a column or table.
- Only SELECT statements are allowed (no INSERT/UPDATE/DELETE/DDL).
- Output raw SQL only: no markdown code fences, no explanation, no comments.
- Use single quotes for string literals.

Schema:
{schema}
"""


class LLMError(Exception):
    """Raised when the Anthropic API call itself fails (auth, network, etc.)."""


def _extract_sql(text: str) -> str:
    """Strip markdown code fences if the model adds them despite instructions."""
    text = text.strip()
    fence_match = re.match(r"^```(?:sql)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    return text.rstrip(";").strip()


def generate_sql(question: str, schema_description: str, previous_sql: str = None,
                  errors=None) -> str:
    """Generate a candidate SQL query for `question`.

    On a repair attempt, pass the previous (invalid) SQL and the list of
    validation error strings from semantic_analyzer/parser; the model is
    asked to fix that specific query rather than start over blind.
    """
    system = SYSTEM_PROMPT.format(schema=schema_description)

    if previous_sql is None:
        user_message = f"Question: {question}"
    else:
        error_list = "\n".join(f"- {e}" for e in (errors or []))
        user_message = (
            f"Question: {question}\n\n"
            f"Your previous SQL was invalid:\n{previous_sql}\n\n"
            f"Validation errors:\n{error_list}\n\n"
            f"Fix the query so it answers the question and passes validation."
        )

    try:
        client = Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=system,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user_message}],
        )
    except TypeError as e:
        # The SDK raises a plain TypeError (not AuthenticationError) when no
        # credential source resolves at all, e.g. ANTHROPIC_API_KEY is unset.
        # A bad-but-present key instead reaches AuthenticationError below.
        if "authentication" not in str(e).lower():
            raise
        raise LLMError(
            "No Anthropic credentials found - set the ANTHROPIC_API_KEY environment "
            f"variable. ({e})"
        ) from e
    except AuthenticationError as e:
        raise LLMError(
            "Anthropic API authentication failed - check that ANTHROPIC_API_KEY is set "
            f"correctly. ({e})"
        ) from e
    except RateLimitError as e:
        raise LLMError(f"Anthropic API rate limit hit: {e}") from e
    except APIConnectionError as e:
        raise LLMError(f"Could not reach the Anthropic API (network issue): {e}") from e
    except APIStatusError as e:
        raise LLMError(f"Anthropic API returned an error: {e}") from e

    text = "".join(block.text for block in response.content if block.type == "text")
    sql = _extract_sql(text)
    if not sql:
        raise LLMError("The model returned an empty response instead of SQL.")
    return sql
