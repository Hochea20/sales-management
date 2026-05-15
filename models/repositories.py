from models.db import get_db


def query_all(query, params=()):
    return get_db().execute(query, params).fetchall()


def query_one(query, params=()):
    return get_db().execute(query, params).fetchone()


def execute(query, params=()):
    db = get_db()
    cursor = db.execute(query, params)
    db.commit()
    return cursor.lastrowid
