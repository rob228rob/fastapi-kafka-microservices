# tests/conftest.py
import pytest
import psycopg2
from fastapi.testclient import TestClient
from unittest.mock import patch
from ...main import app
from psycopg2.extensions import connection as PGConnection
import os

TEST_DB_NAME = os.getenv("TEST_DB_NAME", "test_db")
TEST_DB_USER = os.getenv("TEST_DB_USER", "test_user")
TEST_DB_PASS = os.getenv("TEST_DB_PASS", "test_password")
TEST_DB_HOST = os.getenv("TEST_DB_HOST", "localhost")

@pytest.fixture(scope="session")
def db_connection():
    # Подключаемся к тестовой базе
    conn = psycopg2.connect(
        dbname=TEST_DB_NAME,
        user=TEST_DB_USER,
        password=TEST_DB_PASS,
        host=TEST_DB_HOST
    )
    conn.autocommit = False
    yield conn
    conn.close()

@pytest.fixture(scope="function")
def test_db(db_connection: PGConnection):
    # Начинаем транзакцию
    with db_connection.cursor() as cur:
        cur.execute(open("test.sql", "r").read())
        db_connection.commit()
        pass

    try:
        yield db_connection
    finally:
        # Откатываем все изменения после каждого теста
        db_connection.rollback()

@pytest.fixture(scope="function")
def client(test_db):
    # Мокаем get_connection, чтобы он возвращал наш test_db connection
    with patch("src.db.get_connection", return_value=test_db):
        yield TestClient(app)