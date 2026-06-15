import sqlite3
from create_db import ensure_db

def get_connection():
    ensure_db()
    conn = sqlite3.connect("flights.db", check_same_thread=False)
    return conn