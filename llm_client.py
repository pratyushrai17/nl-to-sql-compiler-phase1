"""
llm_client.py

Thin wrapper around the Anthropic API: turns a natural language question
into a candidate SQL query. repair_loop.py also uses this to ask for a fix,
by passing the previous invalid SQL plus the semantic/syntax errors.

Reads credentials the normal way the Anthropic SDK does (ANTHROPIC_API_KEY
env var, or another resolvable credential source) — no key handling of our
own.

STUB MODE: if ANTHROPIC_API_KEY isn't set, generate_sql() automatically
falls back to STUB_RESPONSES below instead of calling the API or raising.
This keeps `python main.py` demoable with no key configured at all — useful
for a live review where network/credentials might not cooperate. A note is
printed the first time stub mode kicks in so it's never silently pretending
to be the real LLM. Stub mode only knows the built-in demo questions (see
tests/examples.py); anything else raises LLMError explaining that a real
key is needed.
"""

import os
import re

from anthropic import (
    Anthropic,
    AuthenticationError,
    RateLimitError,
    APIStatusError,
    APIConnectionError,
)

MODEL = "claude-sonnet-5"

# Pre-written stand-ins for the LLM, used only when no API key is configured.
# Keyed by the exact question text from tests/examples.py. Each entry has an
# "initial" response (attempt #1) and, for the one deliberately-invalid
# example, a "repair" response returned once errors are fed back — so stub
# mode can still exercise the full validate-then-repair path with no live
# model in the loop.
STUB_RESPONSES = {
    "List the titles and authors of every Dystopian book.": {
        "initial": "SELECT title, author FROM Books WHERE genre = 'Dystopian'",
    },
    "How many books are there in each genre?": {
        "initial": "SELECT genre, COUNT(*) FROM Books GROUP BY genre",
    },
    "For each genre, show the author and how many books there are.": {
        # Deliberately invalid: 'author' is selected alongside COUNT(*) but is
        # neither aggregated nor listed in GROUP BY — the same mistake
        # tests/examples.py seeds directly, reproduced here so stub mode
        # triggers the repair path on its own too.
        "initial": "SELECT genre, author, COUNT(*) FROM Books GROUP BY genre",
        "repair": "SELECT genre, COUNT(*) FROM Books GROUP BY genre",
    },
}

_stub_notice_printed = False

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

    Falls back to stub mode (see module docstring) when ANTHROPIC_API_KEY
    is not set, instead of failing.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _generate_sql_stub(question, previous_sql)
    return _generate_sql_live(question, schema_description, previous_sql, errors)


def _generate_sql_stub(question: str, previous_sql: str = None) -> str:
    global _stub_notice_printed
    if not _stub_notice_printed:
        print(
            "[llm_client] ANTHROPIC_API_KEY not set - running in STUB MODE: "
            "returning pre-written example SQL instead of calling the real LLM."
        )
        _stub_notice_printed = True

    canned = STUB_RESPONSES.get(question)
    if canned is None:
        raise LLMError(
            f"Stub mode has no pre-written response for the question {question!r}. "
            "Set ANTHROPIC_API_KEY to use the real LLM for questions outside the "
            "built-in demo examples."
        )

    if previous_sql is None:
        return canned["initial"]

    repaired = canned.get("repair")
    if repaired is None:
        raise LLMError(
            f"Stub mode has no pre-written repair for the question {question!r}. "
            "Set ANTHROPIC_API_KEY to use the real LLM to repair arbitrary errors."
        )
    return repaired


def _generate_sql_live(question: str, schema_description: str, previous_sql: str = None,
                        errors=None) -> str:
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
