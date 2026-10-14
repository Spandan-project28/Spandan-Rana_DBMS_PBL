"""Small connection-pool wrapper around mysql-connector-python."""
from contextlib import contextmanager

import mysql.connector
from mysql.connector import pooling

import config

_pool = pooling.MySQLConnectionPool(
    pool_name="railway_pool",
    pool_size=3,
    host=config.DB_HOST,
    port=config.DB_PORT,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    database=config.DB_NAME,
    autocommit=False,
)


@contextmanager
def get_connection():
    """Yields a pooled connection. Caller controls commit/rollback."""
    cnx = _pool.get_connection()
    try:
        yield cnx
    finally:
        cnx.close()


@contextmanager
def get_cursor(dictionary=True, commit=True):
    """Yields (cnx, cursor). Commits on clean exit, rolls back on exception."""
    cnx = _pool.get_connection()
    cur = cnx.cursor(dictionary=dictionary)
    try:
        yield cnx, cur
        if commit:
            cnx.commit()
    except Exception:
        cnx.rollback()
        raise
    finally:
        cur.close()
        cnx.close()


class AppError(Exception):
    """A user-facing error: (http_status, message)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status
