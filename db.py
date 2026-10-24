"""Database connections: Supabase Postgres when DATABASE_URL is set, a local SQLite file otherwise.

The app's queries are written once, in SQL both databases understand. This module smooths over the
two differences that remain: placeholders (SQLite's `?` vs Postgres's `%s`) and the row type
(rows support both row["name"] and row[0] either way).
"""
import atexit
import os
import re
import sqlite3


def _load_env_file():
    """Read KEY=value lines from a .env file next to this one (gitignored, holds the secrets).
    Real environment variables, like the ones set on Render, take priority."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USING_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if USING_POSTGRES:
    import psycopg
    from psycopg_pool import ConnectionPool

    IntegrityError = (sqlite3.IntegrityError, psycopg.IntegrityError)
else:
    IntegrityError = (sqlite3.IntegrityError,)


class Row(dict):
    """A Postgres row that works like sqlite3.Row: row["name"], row[0], dict(row), and row.keys()."""
    __slots__ = ("_values",)

    def __init__(self, names, values):
        super().__init__(zip(names, values))
        self._values = values

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, (int, slice)) else dict.__getitem__(self, key)


def _row_factory(cursor):
    names = [column.name for column in cursor.description or []]
    return lambda values: Row(names, values)


def _postgres_sql(sql, params):
    """Rewrite SQLite-style placeholders (? or :name) as psycopg's (%s or %(name)s)."""
    sql = sql.replace("%", "%%")
    if isinstance(params, dict):
        return re.sub(r"(?<![:\w]):(\w+)", r"%(\1)s", sql)
    return sql.replace("?", "%s")


class PostgresConnection:
    """Wraps a pooled psycopg connection with the small slice of the sqlite3 API the app uses."""

    def __init__(self, pool):
        self._pool = pool
        self._conn = pool.getconn()

    def execute(self, sql, params=()):
        cursor = self._conn.cursor(row_factory=_row_factory)
        cursor.execute(_postgres_sql(sql, params), params if params else None)
        return cursor

    def executemany(self, sql, rows):
        rows = list(rows)
        cursor = self._conn.cursor(row_factory=_row_factory)
        if rows:
            cursor.executemany(_postgres_sql(sql, rows[0]), rows)
        return cursor

    def executescript(self, script):
        self._conn.execute(script)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.rollback()  # never leave a half-finished transaction on a pooled connection
        self._pool.putconn(self._conn)


SCHEMA = "sooner_buddies"  # Postgres schema holding the app's tables (created by schema_postgres.sql)


def _use_app_schema(conn):
    """Every pooled connection works inside the app's own schema."""
    conn.execute(f"SET search_path TO {SCHEMA}")
    conn.commit()


_pool = None


def connect(sqlite_path):
    """A new connection for one request."""
    global _pool
    if USING_POSTGRES:
        if _pool is None:
            # prepare_threshold=None keeps this working through Supabase's connection pooler.
            _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5, open=True, configure=_use_app_schema,
                                   kwargs={"prepare_threshold": None, "connect_timeout": 15})
            atexit.register(_pool.close)
        return PostgresConnection(_pool)
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
