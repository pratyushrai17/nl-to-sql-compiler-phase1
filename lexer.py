"""
lexer.py

Hand-written tokenizer for the (small) subset of SQL this project supports:
SELECT, FROM, WHERE, JOIN, ON, GROUP BY, ORDER BY, ASC/DESC, AND/OR, AS,
comparison operators, string/number literals, identifiers, and punctuation.

Phase 1 scope: just enough to tokenize simple SELECT queries with WHERE,
one JOIN, GROUP BY, and ORDER BY. No comments, no escaped-quote handling,
no multi-statement input — that's explicitly deferred to later phases.
"""

import re

KEYWORDS = {
    "SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP", "BY", "ORDER",
    "ASC", "DESC", "AND", "OR", "AS", "INNER", "LEFT",
}

# Order matters: longer operators must be matched before their prefixes
# (e.g. "<=" before "<"), and STRING/NUMBER before IDENT.
TOKEN_SPEC = [
    ("WHITESPACE", r"[ \t\r\n]+"),
    ("STRING",     r"'(?:[^']*)'"),
    ("NUMBER",     r"\d+(?:\.\d+)?"),
    ("LE",         r"<="),
    ("GE",         r">="),
    ("NEQ",        r"(?:!=|<>)"),
    ("EQ",         r"="),
    ("LT",         r"<"),
    ("GT",         r">"),
    ("COMMA",      r","),
    ("DOT",        r"\."),
    ("LPAREN",     r"\("),
    ("RPAREN",     r"\)"),
    ("STAR",       r"\*"),
    ("IDENT",      r"[A-Za-z_][A-Za-z0-9_]*"),
]

_MASTER_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in TOKEN_SPEC))


class Token:
    def __init__(self, type_, value, pos):
        self.type = type_
        self.value = value
        self.pos = pos

    def __repr__(self):
        return f"Token({self.type!r}, {self.value!r})"

    def __eq__(self, other):
        return isinstance(other, Token) and self.type == other.type and self.value == other.value


class LexError(Exception):
    pass


def tokenize(source: str):
    """Turn a raw SQL string into a list of Tokens, ending with an EOF token."""
    tokens = []
    pos = 0
    length = len(source)

    while pos < length:
        match = _MASTER_RE.match(source, pos)
        if not match:
            raise LexError(f"Unexpected character {source[pos]!r} at position {pos}")

        kind = match.lastgroup
        text = match.group()
        pos = match.end()

        if kind == "WHITESPACE":
            continue

        if kind == "STRING":
            tokens.append(Token("STRING", text[1:-1], match.start()))
        elif kind == "NUMBER":
            value = float(text) if "." in text else int(text)
            tokens.append(Token("NUMBER", value, match.start()))
        elif kind == "IDENT":
            upper = text.upper()
            if upper in KEYWORDS:
                tokens.append(Token(upper, text, match.start()))
            else:
                tokens.append(Token("IDENT", text, match.start()))
        else:
            tokens.append(Token(kind, text, match.start()))

    tokens.append(Token("EOF", None, length))
    return tokens
