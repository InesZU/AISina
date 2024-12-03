import sqlite3
from flask import g, current_app

def get_db():
    """Connect to the database."""
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = sqlite3.connect(current_app.config['DATABASE'])
        g.sqlite_db.row_factory = sqlite3.Row
    return g.sqlite_db

def close_db(e=None):
    """Close the database connection."""
    db = g.pop('sqlite_db', None)
    if db is not None:
        db.close()

def init_db():
    """Initialize the database."""
    db = get_db()
    with current_app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit() 