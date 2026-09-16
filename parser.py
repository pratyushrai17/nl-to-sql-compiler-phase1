"""
parser.py

Hand-written recursive-descent parser. Consumes the token list produced by
lexer.tokenize() and builds a SelectStatement AST (ast_nodes.py).

Grammar (Phase 1 subset):

    select_stmt   := SELECT select_list FROM table_ref join_clause*
                      (WHERE condition_expr)?
                      (GROUP BY column_ref ("," column_ref)*)?
                      (ORDER BY order_item ("," order_item)*)?

    select_list   := "*" | select_item ("," select_item)*
    select_item   := (agg_call | column_ref | "*") ("AS" IDENT)?
    agg_call      := IDENT "(" ("*" | column_ref) ")"

    table_ref     := IDENT ("AS" IDENT)?
    join_clause   := ("INNER" | "LEFT")? "JOIN" table_ref "ON" condition

    condition_expr:= condition (("AND" | "OR") condition)*
    condition     := operand comp_op operand
    operand       := column_ref | STRING | NUMBER
    column_ref    := IDENT ("." IDENT)?
    order_item    := column_ref ("ASC" | "DESC")?

No parenthesized boolean expressions, no subqueries, no HAVING — intentionally
out of scope for a Phase 1 prototype (see CLAUDE.md).
"""

from ast_nodes import (
    AggregateCall, ColumnRef, Condition, JoinClause, LogicalExpr,
    OrderByItem, SelectItem, SelectStatement, Star, TableRef, Literal,
)
from symbol_table import AGGREGATE_FUNCTIONS

COMPARISON_OPS = {"EQ": "=", "NEQ": "!=", "LT": "<", "GT": ">", "LE": "<=", "GE": ">="}


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    # -- token stream helpers -------------------------------------------------

    def peek(self):
        return self.tokens[self.pos]

    def advance(self):
        tok = self.tokens[self.pos]
        if tok.type != "EOF":
            self.pos += 1
        return tok

    def check(self, type_):
        return self.peek().type == type_

    def match(self, *types):
        if self.peek().type in types:
            return self.advance()
        return None

    def expect(self, type_):
        tok = self.peek()
        if tok.type != type_:
            raise ParseError(
                f"Expected {type_} but found {tok.type} ({tok.value!r}) at position {tok.pos}"
            )
        return self.advance()

    # -- entry point ------------------------------------------------------------

    def parse(self) -> SelectStatement:
        stmt = self.parse_select_stmt()
        self.expect("EOF")
        return stmt

    # -- grammar rules ------------------------------------------------------------

    def parse_select_stmt(self) -> SelectStatement:
        self.expect("SELECT")
        select_items = self.parse_select_list()
        self.expect("FROM")
        from_table = self.parse_table_ref()

        joins = []
        while self.check("JOIN") or self.check("INNER") or self.check("LEFT"):
            joins.append(self.parse_join_clause())

        where = None
        if self.match("WHERE"):
            where = self.parse_condition_expr()

        group_by = []
        if self.match("GROUP"):
            self.expect("BY")
            group_by.append(self.parse_column_ref())
            while self.match("COMMA"):
                group_by.append(self.parse_column_ref())

        order_by = []
        if self.match("ORDER"):
            self.expect("BY")
            order_by.append(self.parse_order_item())
            while self.match("COMMA"):
                order_by.append(self.parse_order_item())

        return SelectStatement(
            select_items=select_items,
            from_table=from_table,
            joins=joins,
            where=where,
            group_by=group_by,
            order_by=order_by,
        )

    def parse_select_list(self):
        items = [self.parse_select_item()]
        while self.match("COMMA"):
            items.append(self.parse_select_item())
        return items

    def parse_select_item(self) -> SelectItem:
        if self.check("STAR"):
            self.advance()
            expr = Star()
        elif self.check("IDENT") and self.tokens[self.pos].value.upper() in AGGREGATE_FUNCTIONS \
                and self.tokens[self.pos + 1].type == "LPAREN":
            expr = self.parse_agg_call()
        else:
            expr = self.parse_column_ref()

        alias = None
        if self.match("AS"):
            alias = self.expect("IDENT").value

        return SelectItem(expr=expr, alias=alias)

    def parse_agg_call(self) -> AggregateCall:
        func = self.expect("IDENT").value.upper()
        self.expect("LPAREN")
        if self.check("STAR"):
            self.advance()
            arg = Star()
        else:
            arg = self.parse_column_ref()
        self.expect("RPAREN")
        return AggregateCall(func=func, arg=arg)

    def parse_table_ref(self) -> TableRef:
        name = self.expect("IDENT").value
        alias = None
        if self.match("AS"):
            alias = self.expect("IDENT").value
        return TableRef(name=name, alias=alias)

    def parse_join_clause(self) -> JoinClause:
        self.match("INNER")
        self.match("LEFT")
        self.expect("JOIN")
        table = self.parse_table_ref()
        self.expect("ON")
        condition = self.parse_condition()
        return JoinClause(table=table, on=condition)

    def parse_condition_expr(self):
        left = self.parse_condition()
        while self.check("AND") or self.check("OR"):
            op = self.advance().type
            right = self.parse_condition()
            left = LogicalExpr(left=left, op=op, right=right)
        return left

    def parse_condition(self) -> Condition:
        left = self.parse_operand()
        op_tok = self.peek()
        if op_tok.type not in COMPARISON_OPS:
            raise ParseError(
                f"Expected a comparison operator but found {op_tok.type} ({op_tok.value!r}) "
                f"at position {op_tok.pos}"
            )
        self.advance()
        right = self.parse_operand()
        return Condition(left=left, op=COMPARISON_OPS[op_tok.type], right=right)

    def parse_operand(self):
        if self.check("STRING"):
            return Literal(self.advance().value)
        if self.check("NUMBER"):
            return Literal(self.advance().value)
        return self.parse_column_ref()

    def parse_column_ref(self) -> ColumnRef:
        first = self.expect("IDENT").value
        if self.match("DOT"):
            name = self.expect("IDENT").value
            return ColumnRef(table=first, name=name)
        return ColumnRef(table=None, name=first)

    def parse_order_item(self) -> OrderByItem:
        col = self.parse_column_ref()
        direction = "ASC"
        if self.check("ASC") or self.check("DESC"):
            direction = self.advance().type
        return OrderByItem(column=col, direction=direction)


def parse(tokens) -> SelectStatement:
    return Parser(tokens).parse()
