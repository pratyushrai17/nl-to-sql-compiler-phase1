"""
semantic_analyzer.py

Validates a SelectStatement AST against the hardcoded schema in
symbol_table.py. Phase 1 scope, per CLAUDE.md:

  - undefined table detection
  - undefined / ambiguous column detection (including qualified refs and
    table aliases introduced by FROM / JOIN)
  - one aggregate/GROUP BY misuse check: a plain (non-aggregated) selected
    column can't appear alongside an aggregate function unless it's also
    listed in GROUP BY

Returns a list of human-readable error strings (empty list = valid). The
repair_loop feeds these strings straight back to the LLM as the "what to
fix" instruction, so messages are written to be actionable, not just
diagnostic.
"""

from ast_nodes import (
    AggregateCall, ColumnRef, Condition, LogicalExpr, SelectStatement, Star,
)
from symbol_table import column_exists, get_columns, table_exists


class SemanticError(Exception):
    """Raised by analyze_or_raise(); carries the full list of error messages."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def analyze(stmt: SelectStatement):
    """Return a list of semantic error strings. Empty list means valid."""
    errors = []

    scope = _build_table_scope(stmt, errors)
    # If a referenced table doesn't exist, column resolution against it is
    # meaningless — stop here so error messages stay easy to read.
    if errors:
        return errors

    for col in _collect_column_refs(stmt):
        _resolve_column(col, scope, errors)

    errors.extend(_check_aggregate_usage(stmt, scope))

    return errors


def analyze_or_raise(stmt: SelectStatement):
    errors = analyze(stmt)
    if errors:
        raise SemanticError(errors)


# -- table scope --------------------------------------------------------------

def _build_table_scope(stmt: SelectStatement, errors):
    """Map alias-or-table-name -> real table name for every table referenced
    in FROM and JOIN. Reports undefined tables and duplicate aliases."""
    scope = {}

    def add(table_ref):
        if not table_exists(table_ref.name):
            errors.append(f"Table '{table_ref.name}' is not defined in the schema")
            return
        key = table_ref.alias or table_ref.name
        if key in scope:
            errors.append(f"Table name or alias '{key}' is used more than once")
            return
        scope[key] = table_ref.name

    add(stmt.from_table)
    for join in stmt.joins:
        add(join.table)

    return scope


# -- column collection ----------------------------------------------------------

def _collect_column_refs(stmt: SelectStatement):
    """Every ColumnRef anywhere in the AST that needs to resolve to a real
    column: SELECT list, WHERE, JOIN ON, GROUP BY, ORDER BY."""
    refs = []

    for item in stmt.select_items:
        if isinstance(item.expr, ColumnRef):
            refs.append(item.expr)
        elif isinstance(item.expr, AggregateCall) and isinstance(item.expr.arg, ColumnRef):
            refs.append(item.expr.arg)
        # Star needs no resolution.

    for join in stmt.joins:
        refs.extend(_collect_from_condition(join.on))

    if stmt.where is not None:
        refs.extend(_collect_from_condition(stmt.where))

    refs.extend(stmt.group_by)
    refs.extend(item.column for item in stmt.order_by)

    return refs


def _collect_from_condition(expr):
    if isinstance(expr, Condition):
        refs = []
        if isinstance(expr.left, ColumnRef):
            refs.append(expr.left)
        if isinstance(expr.right, ColumnRef):
            refs.append(expr.right)
        return refs
    if isinstance(expr, LogicalExpr):
        return _collect_from_condition(expr.left) + _collect_from_condition(expr.right)
    return []


def _resolve_column(col: ColumnRef, scope: dict, errors: list):
    if col.table is not None:
        real_table = scope.get(col.table)
        if real_table is None:
            errors.append(
                f"Table or alias '{col.table}' used in column '{col.table}.{col.name}' "
                f"is not in scope (not listed in FROM/JOIN)"
            )
            return
        if not column_exists(real_table, col.name):
            errors.append(
                f"Column '{col.name}' does not exist on table '{real_table}' "
                f"(known columns: {', '.join(get_columns(real_table))})"
            )
        return

    # Unqualified column: must resolve unambiguously across all tables in scope.
    matches = [table for table in scope.values() if column_exists(table, col.name)]
    if not matches:
        errors.append(
            f"Column '{col.name}' does not exist on any table in scope "
            f"({', '.join(scope.values())})"
        )
    elif len(matches) > 1:
        errors.append(
            f"Column '{col.name}' is ambiguous - it exists on multiple tables in scope "
            f"({', '.join(matches)}); qualify it, e.g. '{matches[0]}.{col.name}'"
        )


# -- aggregate / GROUP BY misuse check --------------------------------------------

def _check_aggregate_usage(stmt: SelectStatement, scope: dict):
    errors = []

    has_aggregate = any(isinstance(item.expr, AggregateCall) for item in stmt.select_items)
    if not has_aggregate:
        return errors

    plain_columns = [item.expr for item in stmt.select_items if isinstance(item.expr, ColumnRef)]
    if not plain_columns:
        return errors

    if not stmt.group_by:
        for col in plain_columns:
            errors.append(
                f"Column '{col}' is selected alongside an aggregate function but is not "
                f"wrapped in an aggregate and there is no GROUP BY clause; add "
                f"'GROUP BY {col}' or wrap it in an aggregate function"
            )
        return errors

    group_by_keys = {_column_key(c, scope) for c in stmt.group_by}
    for col in plain_columns:
        if _column_key(col, scope) not in group_by_keys:
            errors.append(
                f"Column '{col}' is selected alongside an aggregate function but does not "
                f"appear in the GROUP BY clause"
            )

    return errors


def _column_key(col: ColumnRef, scope: dict):
    """Normalize a column ref to (real_table_or_None, name) so a qualified
    and unqualified reference to the same column compare equal."""
    if col.table is not None:
        return (scope.get(col.table, col.table), col.name)
    return (None, col.name)
