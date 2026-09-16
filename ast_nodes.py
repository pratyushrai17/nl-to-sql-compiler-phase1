"""
ast_nodes.py

AST node definitions for the SELECT-only grammar this project supports.
Plain dataclasses — no behavior beyond a readable repr, which main.py uses
to print the AST during the pipeline demo.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass
class ColumnRef:
    """A column reference, optionally qualified by table name/alias: t.col"""
    table: Optional[str]
    name: str

    def __repr__(self):
        return f"{self.table}.{self.name}" if self.table else self.name


@dataclass
class Star:
    """The `*` wildcard in SELECT * or COUNT(*)."""

    def __repr__(self):
        return "*"


@dataclass
class Literal:
    """A string or number literal, e.g. 'George Orwell' or 5."""
    value: Union[str, int, float]

    def __repr__(self):
        return repr(self.value)


@dataclass
class AggregateCall:
    """An aggregate function call, e.g. COUNT(*) or AVG(Loans.due_date)."""
    func: str  # one of symbol_table.AGGREGATE_FUNCTIONS
    arg: Union[ColumnRef, Star]

    def __repr__(self):
        return f"{self.func}({self.arg})"


@dataclass
class SelectItem:
    """One entry in the SELECT list: a column, a star, or an aggregate call,
    with an optional alias (`AS ...`)."""
    expr: Union[ColumnRef, Star, AggregateCall]
    alias: Optional[str] = None

    def __repr__(self):
        return f"{self.expr} AS {self.alias}" if self.alias else repr(self.expr)


@dataclass
class TableRef:
    """A table name with an optional alias, e.g. `Loans l`."""
    name: str
    alias: Optional[str] = None

    def __repr__(self):
        return f"{self.name} AS {self.alias}" if self.alias else self.name


@dataclass
class Condition:
    """A single comparison, e.g. `Books.genre = 'Fantasy'`."""
    left: Union[ColumnRef, Literal]
    op: str  # =, !=, <>, <, >, <=, >=
    right: Union[ColumnRef, Literal]

    def __repr__(self):
        return f"{self.left} {self.op} {self.right}"


@dataclass
class LogicalExpr:
    """A boolean combination of conditions: left AND/OR right."""
    left: "ConditionExpr"
    op: str  # AND, OR
    right: "ConditionExpr"

    def __repr__(self):
        return f"({self.left} {self.op} {self.right})"


ConditionExpr = Union[Condition, LogicalExpr]


@dataclass
class JoinClause:
    """A single JOIN <table> ON <condition>."""
    table: TableRef
    on: Condition


@dataclass
class OrderByItem:
    column: ColumnRef
    direction: str = "ASC"  # ASC or DESC

    def __repr__(self):
        return f"{self.column} {self.direction}"


@dataclass
class SelectStatement:
    """Root AST node for a full SELECT query."""
    select_items: List[SelectItem]
    from_table: TableRef
    joins: List[JoinClause] = field(default_factory=list)
    where: Optional[ConditionExpr] = None
    group_by: List[ColumnRef] = field(default_factory=list)
    order_by: List[OrderByItem] = field(default_factory=list)
