"""
visualize.py

Runs the same 3 hardcoded example questions (tests/examples.py) through the
real pipeline (repair_loop.run_pipeline) and renders the result as a single
self-contained HTML file (demo_output.html) — tokens as boxes, the AST as an
actual connected-box tree diagram, validation results, repair attempts side
by side, and final query results as a table.

No external dependencies: everything (CSS, tree-drawing) is inline, so the
output file can be opened by double-clicking it — no server, no JS libraries.

Run with:  python visualize.py
"""

import html
import webbrowser
from pathlib import Path

from ast_nodes import AggregateCall, LogicalExpr, SelectStatement
from db import get_connection, run_query
from repair_loop import run_pipeline
from tests.examples import EXAMPLES

OUTPUT_PATH = Path(__file__).resolve().parent / "demo_output.html"


# -- AST -> generic tree structure -------------------------------------------------
#
# Rather than a generic dataclass dump, this builds a tree shaped like the
# query itself (SELECT / FROM / JOIN / WHERE / GROUP BY / ORDER BY as
# top-level branches, WHERE conditions recursing through AND/OR) — closer to
# how an AST is usually drawn on a whiteboard than a field-by-field dump.

def _node(label, children=None):
    return {"label": str(label), "children": children or []}


def _condition_tree(expr):
    if isinstance(expr, LogicalExpr):
        return _node(expr.op, [_condition_tree(expr.left), _condition_tree(expr.right)])
    return _node(repr(expr))  # a Condition leaf, e.g. "genre = 'Dystopian'"


def _select_item_tree(item):
    if isinstance(item.expr, AggregateCall):
        agg = item.expr
        n = _node(f"{agg.func}(...)", [_node(repr(agg.arg))])
    else:
        n = _node(repr(item.expr))
    if item.alias:
        n["label"] += f" AS {item.alias}"
    return n


def _join_tree(join):
    return _node(f"JOIN {join.table!r}", [_node("ON", [_condition_tree(join.on)])])


def ast_to_tree(stmt: SelectStatement):
    children = [_node("SELECT", [_select_item_tree(i) for i in stmt.select_items])]
    children.append(_node("FROM", [_node(repr(stmt.from_table))]))

    for join in stmt.joins:
        children.append(_join_tree(join))

    if stmt.where is not None:
        children.append(_node("WHERE", [_condition_tree(stmt.where)]))

    if stmt.group_by:
        children.append(_node("GROUP BY", [_node(repr(c)) for c in stmt.group_by]))

    if stmt.order_by:
        children.append(_node("ORDER BY", [_node(repr(o)) for o in stmt.order_by]))

    return _node("SelectStatement", children)


# -- HTML rendering ----------------------------------------------------------------

def esc(value) -> str:
    return html.escape(str(value), quote=True)


def render_tree_node(node) -> str:
    children_html = ""
    if node["children"]:
        children_html = "<ul>" + "".join(render_tree_node(c) for c in node["children"]) + "</ul>"
    return f"<li><span class='tree-node'>{esc(node['label'])}</span>{children_html}</li>"


def render_tree(root) -> str:
    return f"<ul class='tree'>{render_tree_node(root)}</ul>"


def render_tokens(tokens) -> str:
    if tokens is None:
        return "<p class='muted'>(tokenization failed before any tokens were produced)</p>"
    shown = [t for t in tokens if t.type != "EOF"]
    boxes = "".join(
        f"<div class='token-box'><div class='token-type'>{esc(t.type)}</div>"
        f"<div class='token-value'>{esc(t.value)}</div></div>"
        for t in shown
    )
    return f"<div class='token-row'>{boxes}</div>"


def render_validation(attempt) -> str:
    if attempt.valid:
        return "<div class='validation ok'><span class='check'>&#10003;</span> Valid</div>"
    errors_html = "".join(f"<li>{esc(e)}</li>" for e in attempt.errors)
    return (
        "<div class='validation fail'><span class='cross'>&#10007;</span> Invalid"
        f"<ul class='error-list'>{errors_html}</ul></div>"
    )


def render_attempt_card(attempt) -> str:
    ast_html = render_tree(ast_to_tree(attempt.ast)) if attempt.ast is not None else (
        "<p class='muted'>(no AST — parsing did not succeed)</p>"
    )
    return f"""
    <div class="attempt-card">
      <div class="attempt-header">Attempt {attempt.number} <span class="source">({esc(attempt.source)})</span></div>
      <div class="sql-box">{esc(attempt.sql)}</div>
      <div class="block-label">Tokens</div>
      {render_tokens(attempt.tokens)}
      <div class="block-label">AST</div>
      <div class="tree-wrap">{ast_html}</div>
      <div class="block-label">Validation</div>
      {render_validation(attempt)}
    </div>
    """


def render_results_table(columns, rows) -> str:
    if not rows:
        return "<p class='muted'>(no rows returned)</p>"
    head = "".join(f"<th>{esc(c)}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(v)}</td>" for v in row) + "</tr>"
        for row in rows
    )
    return f"<table class='results'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_example(conn, example, index) -> str:
    result = run_pipeline(
        question=example["question"],
        max_retries=2,
        seed_sql=example.get("seed_sql"),
    )

    attempts_html = "".join(render_attempt_card(a) for a in result.attempts)
    side_by_side_class = "attempts-row multi" if len(result.attempts) > 1 else "attempts-row"

    if result.success:
        final_sql = result.final.sql
        columns, rows = run_query(conn, final_sql)
        outcome_html = f"""
        <div class="final-sql-box">
          <div class="block-label">Final validated SQL</div>
          <div class="sql-box final">{esc(final_sql)}</div>
        </div>
        <div class="block-label">Query results</div>
        {render_results_table(columns, rows)}
        """
        badge = "<span class='badge ok'>SUCCESS</span>"
    else:
        outcome_html = (
            "<p class='muted'>Pipeline did not produce a valid query "
            f"after {len(result.attempts)} attempt(s).</p>"
        )
        badge = "<span class='badge fail'>FAILED</span>"

    return f"""
    <section class="example" id="example-{index}">
      <h2>Example {index} {badge}</h2>
      <div class="question">&ldquo;{esc(example['question'])}&rdquo;</div>
      <div class="{side_by_side_class}">{attempts_html}</div>
      {outcome_html}
    </section>
    """


CSS = """
:root {
  color-scheme: light;
  --bg: #f4f6f8;
  --card-bg: #ffffff;
  --border: #d7dce1;
  --text: #1f2937;
  --muted: #6b7280;
  --accent: #2563eb;
  --ok-bg: #e8f5e9;
  --ok-fg: #2e7d32;
  --fail-bg: #fdecea;
  --fail-fg: #c62828;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 24px 16px 64px;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
}
.page-title { text-align: center; margin: 0 0 4px; font-size: 28px; }
.page-subtitle { text-align: center; color: var(--muted); margin: 0 0 24px; }
.toc {
  max-width: 720px;
  margin: 0 auto 40px;
  display: flex;
  justify-content: center;
  gap: 16px;
  flex-wrap: wrap;
}
.toc a {
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--card-bg);
}
.toc a:hover { background: #eef2ff; }

.example {
  max-width: 1100px;
  margin: 0 auto 56px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px 28px 32px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.example h2 { margin-top: 0; display: flex; align-items: center; gap: 12px; }
.badge {
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 12px;
  letter-spacing: 0.03em;
}
.badge.ok { background: var(--ok-bg); color: var(--ok-fg); }
.badge.fail { background: var(--fail-bg); color: var(--fail-fg); }

.question {
  font-size: 18px;
  font-style: italic;
  color: #374151;
  margin: 4px 0 24px;
  padding: 12px 16px;
  background: #f9fafb;
  border-left: 4px solid var(--accent);
  border-radius: 4px;
}

.attempts-row {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}
.attempts-row.multi .attempt-card { flex: 1 1 420px; }
.attempts-row:not(.multi) .attempt-card { flex: 1 1 100%; }

.attempt-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px;
  background: #fcfcfd;
}
.attempt-header { font-weight: 700; margin-bottom: 10px; }
.attempt-header .source { font-weight: 400; color: var(--muted); font-size: 13px; }

.block-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  margin: 14px 0 6px;
  font-weight: 700;
}
.sql-box {
  font-family: "Consolas", "Menlo", monospace;
  font-size: 14px;
  background: #0f172a;
  color: #e2e8f0;
  padding: 10px 14px;
  border-radius: 6px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.sql-box.final { background: #14532d; color: #ecfdf5; }

.token-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.token-box {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  padding: 4px 8px;
  text-align: center;
  min-width: 44px;
}
.token-type {
  font-size: 10px;
  color: var(--accent);
  font-weight: 700;
  text-transform: uppercase;
}
.token-value {
  font-family: monospace;
  font-size: 13px;
  word-break: break-word;
}

.validation {
  display: inline-flex;
  flex-direction: column;
  padding: 8px 14px;
  border-radius: 6px;
  font-weight: 600;
}
.validation.ok { background: var(--ok-bg); color: var(--ok-fg); }
.validation.fail { background: var(--fail-bg); color: var(--fail-fg); }
.validation .check, .validation .cross { margin-right: 6px; }
.error-list { margin: 8px 0 0; padding-left: 20px; font-weight: 400; font-size: 13px; }

.final-sql-box { margin-top: 8px; }

table.results {
  border-collapse: collapse;
  width: 100%;
  font-size: 14px;
  margin-top: 6px;
}
table.results th, table.results td {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}
table.results th { background: #f3f4f6; }
table.results tr:nth-child(even) td { background: #fafafa; }

.muted { color: var(--muted); font-style: italic; }

/* -- pure-CSS connected-box tree ------------------------------------------- */
.tree-wrap { overflow-x: auto; padding: 8px 0 4px; }
.tree, .tree ul, .tree li {
  list-style: none;
  margin: 0;
  padding: 0;
  position: relative;
}
.tree {
  display: inline-flex;
  justify-content: center;
  padding-top: 10px;
  min-width: 100%;
}
.tree ul {
  display: flex;
  padding-top: 20px;
  position: relative;
}
.tree li {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 10px 0 10px;
  position: relative;
}
.tree li::before, .tree li::after {
  content: '';
  position: absolute;
  top: 0;
  right: 50%;
  width: 50%;
  height: 20px;
  border-top: 2px solid #9ca3af;
}
.tree li::after { right: auto; left: 50%; border-left: 2px solid #9ca3af; }
.tree li:only-child::after, .tree li:only-child::before { display: none; }
.tree li:only-child { padding-top: 0; }
.tree li:first-child::before { border: 0 none; }
.tree li:last-child::after { border: 0 none; }
.tree li:last-child::before { border-right: 2px solid #9ca3af; border-radius: 0 6px 0 0; }
.tree li:first-child::after { border-radius: 6px 0 0 0; }
.tree ul ul::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  border-left: 2px solid #9ca3af;
  width: 0;
  height: 20px;
}
.tree li .tree-node {
  border: 1px solid #9ca3af;
  border-radius: 5px;
  background: #fff;
  padding: 5px 10px;
  font-family: monospace;
  font-size: 12px;
  white-space: nowrap;
  display: inline-block;
}
"""


def build_html(sections_html: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NL to SQL Pipeline Demo</title>
<style>{CSS}</style>
</head>
<body>
  <h1 class="page-title">NL &rarr; SQL Compiler Pipeline</h1>
  <p class="page-subtitle">Phase 1 prototype demo &mdash; generated by visualize.py from a live pipeline run</p>
  <nav class="toc">
    <a href="#example-1">Example 1</a>
    <a href="#example-2">Example 2</a>
    <a href="#example-3">Example 3</a>
  </nav>
  {sections_html}
</body>
</html>
"""


def main():
    conn = get_connection()
    sections = []
    for i, example in enumerate(EXAMPLES, start=1):
        print(f"Running example {i}: {example['question']}")
        sections.append(render_example(conn, example, i))
    conn.close()

    html_doc = build_html("".join(sections))
    OUTPUT_PATH.write_text(html_doc, encoding="utf-8")
    print(f"\nWrote {OUTPUT_PATH} ({len(html_doc):,} bytes)")
    return OUTPUT_PATH


if __name__ == "__main__":
    path = main()
    # Open it for convenience; harmless if there's no display available.
    try:
        webbrowser.open(path.as_uri())
    except Exception:
        pass
