import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock

import psycopg2
from psycopg2 import sql
import pytest

from app.db import database, migrate


@pytest.fixture
def connection(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    monkeypatch.setattr(migrate, "get_conn", Mock(return_value=connection))
    return connection, cursor


def test_migrations_apply_in_order_and_are_recorded(connection, tmp_path):
    (tmp_path / "002_second.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    conn, cursor = connection
    assert migrate.apply_migrations(tmp_path) == ["001_first.sql", "002_second.sql"]
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert statements.index("SELECT 1;") < statements.index("SELECT 2;")
    inserts = [call.args[1][0] for call in cursor.execute.call_args_list
               if call.args[0].startswith("INSERT INTO public.schema_migrations")]
    assert inserts == ["001_first.sql", "002_second.sql"]
    conn.__exit__.assert_called_once_with(None, None, None)
    conn.close.assert_called_once()


def test_applied_migrations_are_not_repeated(connection):
    _, cursor = connection
    migrations = migrate.load_migrations(migrate.MIGRATIONS_DIR)
    cursor.fetchall.return_value = [(name, checksum) for name, checksum, _ in migrations]
    assert migrate.apply_migrations() == []
    assert not any(
        "CREATE TABLE IF NOT EXISTS public.places" in call.args[0]
        for call in cursor.execute.call_args_list
    )


@pytest.mark.parametrize("history", [
    [("999_missing.sql", "checksum")],
    [("001_initial_schema.sql", "modified")],
])
def test_changed_or_missing_migrations_fail_before_schema_changes(connection, history):
    conn, cursor = connection
    cursor.fetchall.return_value = history
    with pytest.raises(RuntimeError, match="history differs"):
        migrate.apply_migrations()
    assert not any(
        "CREATE TABLE IF NOT EXISTS public.places" in call.args[0]
        for call in cursor.execute.call_args_list
    )
    assert conn.__exit__.call_args.args[0] is RuntimeError
    conn.close.assert_called_once()


@pytest.mark.parametrize("files", [
    {}, {"bad.sql": "SELECT 1;"}, {"001_empty.sql": ""},
    {"001_a.sql": "SELECT 1;", "001_b.sql": "SELECT 2;"},
])
def test_invalid_migrations_do_not_connect(monkeypatch, tmp_path, files):
    connect = Mock()
    monkeypatch.setattr(migrate, "get_conn", connect)
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        migrate.apply_migrations(tmp_path)
    connect.assert_not_called()


def test_failed_migration_exits_transaction_and_closes_connection(connection, tmp_path):
    conn, cursor = connection
    (tmp_path / "001_broken.sql").write_text("BROKEN SQL;", encoding="utf-8")
    def execute(statement, *args):
        if statement == "BROKEN SQL;":
            raise psycopg2.ProgrammingError("invalid SQL")
    cursor.execute.side_effect = execute
    with pytest.raises(psycopg2.ProgrammingError):
        migrate.apply_migrations(tmp_path)
    assert conn.__exit__.call_args.args[0] is psycopg2.ProgrammingError
    conn.close.assert_called_once()


@pytest.fixture
def postgres(monkeypatch):
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN is not configured")
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    name = "migration_test_" + uuid.uuid4().hex
    with admin.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    def connect():
        return psycopg2.connect(dsn, dbname=name)
    monkeypatch.setattr(migrate, "get_conn", connect)
    monkeypatch.setattr(database, "get_conn", connect)
    try:
        yield connect
    finally:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
        admin.close()


def test_postgres_schema_supports_repository_operations(postgres):
    assert migrate.apply_migrations() == ["001_initial_schema.sql"]
    assert migrate.apply_migrations() == []
    database.sync_places([{
        "id": "old", "name": "Old", "coords": {"lat": 59.94, "lon": 30.33},
        "image_filename": "old.jpg", "image_source": "original",
    }])
    database.sync_places([{"id": "new", "name": "New"}])
    database.sync_places([{"id": "old", "name": "Updated"}])
    places = {place["id"]: place for place in database.get_all_places()}
    assert set(places) == {"old", "new"}
    assert places["old"]["name"] == "Updated"
    assert places["old"]["image_filename"] == "old.jpg"
    assert places["old"]["image_source"] == "original"
    assert database.get_all_metro_stations() == []


def test_postgres_existing_compatible_tables_keep_data(postgres):
    initial = Path(migrate.MIGRATIONS_DIR / "001_initial_schema.sql").read_text(encoding="utf-8")
    conn = postgres()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(initial)
                cursor.execute("INSERT INTO public.places (id, name) VALUES ('existing', 'Existing')")
    finally:
        conn.close()
    assert migrate.apply_migrations() == ["001_initial_schema.sql"]
    assert database.get_all_places()[0]["id"] == "existing"


def test_postgres_failed_batch_rolls_back(postgres, tmp_path):
    initial = migrate.MIGRATIONS_DIR / "001_initial_schema.sql"
    (tmp_path / initial.name).write_text(initial.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "002_broken.sql").write_text("SELECT missing_column FROM public.places;", encoding="utf-8")
    with pytest.raises(psycopg2.Error):
        migrate.apply_migrations(tmp_path)
    conn = postgres()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.places'), to_regclass('public.schema_migrations')")
            assert cursor.fetchone() == (None, None)
    finally:
        conn.close()
