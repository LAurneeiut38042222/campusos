import os

import pymysql
from flask import g
from pymysql.cursors import DictCursor


def get_db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
            port=int(os.environ.get("MYSQL_PORT", "3306")),
            user="campusos",
            password=os.environ["MYSQL_PASSWORD"],
            database="campusos",
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=5,
        )
    return g.db


def close_db(error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def fetch_one(sql, params=()):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def fetch_all(sql, params=()):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def execute(sql, params=()):
    with get_db().cursor() as cursor:
        cursor.execute(sql, params)
