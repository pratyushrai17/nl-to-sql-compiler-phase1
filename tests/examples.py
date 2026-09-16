"""
tests/examples.py

The example questions used both by main.py (the live pipeline demo) and by
tests/test_pipeline.py. Three examples, per CLAUDE.md Phase 1 scope:

  1. A straightforward WHERE query — should pass validation on the LLM's
     first attempt.
  2. A GROUP BY + aggregate query — should also pass on the first attempt.
  3. A deliberately-seeded invalid query (aggregate/GROUP BY misuse) that
     fails semantic validation, gets the error fed back to the LLM, and is
     repaired.

Why example 3 has a hardcoded `seed_sql` instead of leaving attempt #1 to
the LLM: a capable model given the question *and* the schema often gets it
right on the first try, which would make the "validation fails, then gets
repaired" path a coin flip during a live demo. Seeding a known-bad first
attempt (a real, plausible LLM mistake — selecting a non-aggregated,
non-grouped column) makes the repair path reliably demoable, while the
repair itself is still a genuine LLM call driven by the real error message.
See repair_loop.run_pipeline().
"""

EXAMPLES = [
    {
        "question": "List the titles and authors of every Dystopian book.",
        "seed_sql": None,
    },
    {
        "question": "How many books are there in each genre?",
        "seed_sql": None,
    },
    {
        "question": "For each genre, show the author and how many books there are.",
        # Invalid: 'author' is selected alongside COUNT(*) but is neither
        # aggregated nor listed in GROUP BY — trips the aggregate/GROUP BY
        # misuse check in semantic_analyzer.py every time.
        "seed_sql": "SELECT genre, author, COUNT(*) FROM Books GROUP BY genre",
    },
]
