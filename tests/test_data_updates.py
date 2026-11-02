import json
from unittest.mock import MagicMock, Mock
from urllib.error import URLError

import pytest

import config
import run_parser
from db import database
from parser.attractions import PeterburgCenterParser
from utils import utils


@pytest.fixture
def connection(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(database, "get_conn", Mock(return_value=connection))
    execute = Mock()
    monkeypatch.setattr(database, "execute_values", execute)
    return connection, cursor, execute


def test_parser_image_configuration():
    assert config.PETERBURG_IMAGES_DIR == config.PLACES_IMAGES_DIR
    assert config.PETERBURG_IMAGES_DIR == config.DATA_DIR / "places_images"
    assert PeterburgCenterParser.__init__.__defaults__[0] == config.PETERBURG_IMAGES_DIR


def test_sync_only_upserts_and_does_not_delete_missing_places(connection):
    conn, cursor, execute = connection
    database.sync_places([{"id": "new-place", "name": "New place"}])
    execute.assert_called_once()
    sql = execute.call_args.args[1].upper()
    assert "INSERT INTO PUBLIC.PLACES" in sql
    assert "ON CONFLICT (ID) DO UPDATE" in sql
    assert "DELETE" not in sql
    cursor.execute.assert_not_called()
    assert execute.call_args.args[2][0][0] == "new-place"
    conn.__exit__.assert_called_once_with(None, None, None)
    conn.close.assert_called_once()


def test_sync_preserves_previous_photo_when_download_failed(connection):
    _, _, execute = connection
    database.sync_places([{"id": "existing-place", "image_filename": None, "image_source": None}])
    sql = " ".join(execute.call_args.args[1].split())
    assert "COALESCE(EXCLUDED.image_filename, places.image_filename)" in sql
    assert "ELSE places.image_source" in sql


@pytest.mark.parametrize("data", [[], [{"name": "No ID"}], [{"id": "1"}, {"id": "1"}]])
def test_invalid_sync_input_does_not_open_connection(monkeypatch, data):
    connect = Mock()
    monkeypatch.setattr(database, "get_conn", connect)
    with pytest.raises(ValueError):
        database.sync_places(data)
    connect.assert_not_called()


def test_sync_failure_exits_transaction_and_closes_connection(connection):
    conn, _, execute = connection
    error = RuntimeError("write failed")
    execute.side_effect = error
    with pytest.raises(RuntimeError, match="write failed"):
        database.sync_places([{"id": "1"}])
    assert conn.__exit__.call_args.args[0] is RuntimeError
    assert conn.__exit__.call_args.args[1] is error
    conn.close.assert_called_once()


@pytest.fixture
def parser_backend(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    geo = Mock()
    peterburg = Mock()
    geo.parse.return_value = []
    peterburg.parse.return_value = []
    monkeypatch.setattr(run_parser, "GeoapifyParser", Mock(return_value=geo))
    monkeypatch.setattr(run_parser, "PeterburgCenterParser", Mock(return_value=peterburg))
    monkeypatch.setattr(run_parser, "finalize_all", lambda places: places)
    monkeypatch.setattr(run_parser, "deduplicate", lambda places: places)
    monkeypatch.setattr(run_parser, "print_report", Mock())
    sync = Mock()
    reload_model = Mock(return_value=True)
    monkeypatch.setattr(run_parser, "sync_places", sync)
    monkeypatch.setattr(run_parser, "reload_ml_model", reload_model)
    image = tmp_path / "data" / "places_images" / "old.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"old image")
    catalog = tmp_path / "data" / "places.json"
    catalog.write_text('[{"id":"old"}]', encoding="utf-8")
    return geo, peterburg, sync, reload_model, image, catalog


@pytest.mark.parametrize("failure", ["first", "second", "empty", "database"])
def test_failed_collection_preserves_existing_files(parser_backend, failure):
    geo, peterburg, sync, reload_model, image, catalog = parser_backend
    if failure == "first":
        geo.parse.side_effect = RuntimeError("first parser failed")
    elif failure == "second":
        geo.parse.return_value = [{"id": "new"}]
        peterburg.parse.side_effect = RuntimeError("second parser failed")
    elif failure == "database":
        geo.parse.return_value = [{"id": "new"}]
        sync.side_effect = RuntimeError("database failed")
    with pytest.raises(RuntimeError):
        run_parser.main()
    assert image.read_bytes() == b"old image"
    assert json.loads(catalog.read_text(encoding="utf-8")) == [{"id": "old"}]
    reload_model.assert_not_called()
    if failure != "database":
        sync.assert_not_called()


def test_partial_collection_only_passes_received_places_to_upsert(parser_backend):
    geo, _, sync, reload_model, image, catalog = parser_backend
    geo.parse.return_value = [{"id": "new"}]
    run_parser.main()
    sync.assert_called_once_with([{"id": "new"}])
    reload_model.assert_called_once_with()
    assert image.read_bytes() == b"old image"
    assert json.loads(catalog.read_text(encoding="utf-8")) == [{"id": "old"}]


def test_json_write_failure_preserves_previous_file(monkeypatch, tmp_path):
    path = tmp_path / "places.json"
    path.write_text('[{"id":"old"}]', encoding="utf-8")
    def fail_dump(data, stream, **kwargs):
        stream.write("partial")
        raise OSError("disk failure")
    monkeypatch.setattr(utils.json, "dump", fail_dump)
    assert utils.save_to_json([{"id": "new"}], path) is False
    assert path.read_text(encoding="utf-8") == '[{"id":"old"}]'
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_write_success_replaces_file(tmp_path):
    path = tmp_path / "places.json"
    path.write_text("old", encoding="utf-8")
    assert utils.save_to_json([{"id": "new"}], path) is True
    assert json.loads(path.read_text(encoding="utf-8")) == [{"id": "new"}]
    assert list(tmp_path.glob("*.tmp")) == []


def test_parser_sends_reload_token(monkeypatch):
    monkeypatch.setattr(run_parser, "RELOAD_MODEL_TOKEN", "test-service-token")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"status":"success"}'
    urlopen = Mock(return_value=response)
    monkeypatch.setattr(run_parser, "urlopen", urlopen)
    assert run_parser.reload_ml_model() is True
    request = urlopen.call_args.args[0]
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer test-service-token"
    assert request.data == b""


def test_parser_does_not_request_reload_without_token(monkeypatch):
    monkeypatch.setattr(run_parser, "RELOAD_MODEL_TOKEN", "")
    urlopen = Mock()
    monkeypatch.setattr(run_parser, "urlopen", urlopen)
    assert run_parser.reload_ml_model() is False
    urlopen.assert_not_called()


def test_parser_reports_reload_failure(monkeypatch):
    monkeypatch.setattr(run_parser, "RELOAD_MODEL_TOKEN", "test-service-token")
    monkeypatch.setattr(run_parser, "urlopen", Mock(side_effect=URLError("unavailable")))
    assert run_parser.reload_ml_model() is False
