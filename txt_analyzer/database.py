from __future__ import annotations
import sqlite3
from .config import DB_PATH

def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def init_db() -> None:
    with db_connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS names (
            id INTEGER PRIMARY KEY,
            canonical TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            variant TEXT NOT NULL,
            UNIQUE(canonical, category, variant)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS origin_words (
            id INTEGER PRIMARY KEY,
            language TEXT NOT NULL,
            word TEXT NOT NULL,
            normalized_word TEXT NOT NULL,
            UNIQUE(language, normalized_word)
        )""")

init_db()