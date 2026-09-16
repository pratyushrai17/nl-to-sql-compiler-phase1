"""
db.py

In-memory SQLite database seeded with sample data matching symbol_table.SCHEMA.
Phase 1 only needs enough rows to make example queries return interesting,
readable results during a live demo.
"""

import sqlite3

_BOOKS = [
    (1, "1984", "George Orwell", "Dystopian"),
    (2, "Animal Farm", "George Orwell", "Satire"),
    (3, "Brave New World", "Aldous Huxley", "Dystopian"),
    (4, "The Hobbit", "J.R.R. Tolkien", "Fantasy"),
    (5, "The Fellowship of the Ring", "J.R.R. Tolkien", "Fantasy"),
    (6, "Dune", "Frank Herbert", "Science Fiction"),
    (7, "Foundation", "Isaac Asimov", "Science Fiction"),
    (8, "Pride and Prejudice", "Jane Austen", "Romance"),
]

_MEMBERS = [
    (1, "Alice Rao", "2023-01-10"),
    (2, "Ben Chen", "2023-03-22"),
    (3, "Carla Diaz", "2024-02-14"),
]

_LOANS = [
    (1, 1, 1, "2024-05-01"),
    (2, 4, 2, "2024-05-10"),
    (3, 6, 1, "2024-06-01"),
    (4, 8, 3, "2024-06-15"),
]


def get_connection() -> sqlite3.Connection:
    """Create a fresh in-memory DB, create the schema, and seed sample data."""
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE Books (
            id INTEGER PRIMARY KEY,
            title TEXT,
            author TEXT,
            genre TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE Members (
            id INTEGER PRIMARY KEY,
            name TEXT,
            joined_on TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE Loans (
            id INTEGER PRIMARY KEY,
            book_id INTEGER,
            member_id INTEGER,
            due_date TEXT
        )
    """)

    cur.executemany("INSERT INTO Books VALUES (?, ?, ?, ?)", _BOOKS)
    cur.executemany("INSERT INTO Members VALUES (?, ?, ?)", _MEMBERS)
    cur.executemany("INSERT INTO Loans VALUES (?, ?, ?, ?)", _LOANS)

    conn.commit()
    return conn


def run_query(conn: sqlite3.Connection, sql: str):
    """Execute a validated SELECT and return (column_names, rows)."""
    cur = conn.cursor()
    cur.execute(sql)
    columns = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    return columns, rows
