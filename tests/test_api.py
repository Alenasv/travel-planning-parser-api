from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from api import api


@pytest.fixture
def place():
    return {
        "id": "museum-1",
        "name": "Музей",
        "category": "Культура",
        "metro": None,
        "address": None,
        "work_time": None,
        "coords": {"lat": 59.94, "lon": 30.33},
        "_idx": 0,
        "_score": 0.9,
    }


@pytest.fixture
def backend(monkeypatch, place):
    recommender = Mock()
    recommender.places = [place]
    recommender.recommend.return_value = [place]
    recommender.build_clusters.return_value = [
        {"id": 1, "key": "culture", "name": "Культура и музеи", "tags": ["Культура"], "places": [place]}
    ]
    places = Mock(return_value=[place])
    stations = Mock(return_value=[{"name": "Невский проспект", "lat": 59.935, "lon": 30.328}])
    factory = Mock(return_value=recommender)
    monkeypatch.setattr(api, "model", None)
    monkeypatch.setattr(api, "RELOAD_MODEL_TOKEN", "test-reload-token")
    monkeypatch.setattr(api, "get_all_places", places)
    monkeypatch.setattr(api, "get_all_metro_stations", stations)
    monkeypatch.setattr(api, "build_recommender", factory)
    return recommender, places, stations, factory


@pytest.fixture
def client(backend):
    with TestClient(api.app) as client:
        yield client


def test_startup_and_shutdown(backend, place):
    recommender, places, _, factory = backend
    with TestClient(api.app) as client:
        assert client.get("/ping").status_code == 200
        places.assert_called_once_with()
        factory.assert_called_once_with([place])
        assert api.model is recommender
    assert api.model is None


def test_startup_rejects_empty_database(backend):
    backend[1].return_value = []
    with pytest.raises(RuntimeError, match="нет мест"):
        with TestClient(api.app):
            pass
    backend[3].assert_not_called()
    assert api.model is None


def test_startup_model_failure(backend):
    backend[3].side_effect = RuntimeError("model unavailable")
    with pytest.raises(RuntimeError, match="model unavailable"):
        with TestClient(api.app):
            pass
    assert api.model is None


@pytest.mark.parametrize("path", ["/", "/ping"])
def test_health(client, path):
    response = client.get(path)
    assert response.status_code == 200
    body = response.json()
    assert body.get("status") in ("ok", "running")


def test_recommend_android_contract(client, backend):
    response = client.post(
        "/recommend",
        json={"user_preferences": ["Культура и музеи"], "top_k": 3, "start_metro": "Невский проспект"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "places": [{
            "id": "museum-1", "name": "Музей", "category": "Культура",
            "metro": None, "address": None, "work_time": None,
        }]
    }
    backend[0].recommend.assert_called_once_with(
        user_preferences=["Культура и музеи"], metro_name="Невский проспект", top_k=3,
    )


def test_recommend_defaults(client, backend):
    response = client.post("/recommend", json={"user_preferences": []})
    assert response.status_code == 200
    backend[0].recommend.assert_called_once_with(user_preferences=[], metro_name=None, top_k=10)


def test_recommend_forwards_coordinates(client, backend):
    location = {"lat": 59.94, "lon": 30.33}
    response = client.post(
        "/recommend",
        json={"user_preferences": ["culture"], "top_k": 5, "user_location": location},
    )
    assert response.status_code == 200
    backend[0].recommend.assert_called_once_with(
        user_preferences=["culture"], metro_name=None, top_k=5, user_location=location,
    )


@pytest.mark.parametrize("payload", [
    {},
    {"user_preferences": None},
    {"user_preferences": "culture"},
    {"user_preferences": [None]},
    {"user_preferences": [1]},
    {"user_preferences": [], "top_k": 0},
    {"user_preferences": [], "top_k": -1},
    {"user_preferences": [], "top_k": 11},
    {"user_preferences": [], "top_k": 2.5},
    {"user_preferences": [], "top_k": True},
    {"user_preferences": [], "top_k": "3"},
    {"user_preferences": [], "start_metro": []},
    {"user_preferences": [], "user_location": {"lat": 91, "lon": 30}},
    {"user_preferences": [], "user_location": {"lat": 59, "lon": -181}},
    {"user_preferences": [], "user_location": {"lat": 59}},
    {"user_preferences": [], "user_location": {"lat": "NaN", "lon": 30}},
    {"user_preferences": [], "user_location": {"lat": 59, "lon": "Infinity"}},
])
def test_invalid_request_does_not_call_model(client, backend, payload):
    response = client.post("/recommend", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    backend[0].recommend.assert_not_called()


def test_malformed_json(client, backend):
    response = client.post(
        "/recommend", content='{"user_preferences":', headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    backend[0].recommend.assert_not_called()


@pytest.mark.parametrize("top_k", [1, 10])
def test_top_k_boundaries(client, backend, top_k):
    response = client.post("/recommend", json={"user_preferences": [], "top_k": top_k})
    assert response.status_code == 200
    assert backend[0].recommend.call_args.kwargs["top_k"] == top_k


def test_empty_recommendations(client, backend):
    backend[0].recommend.return_value = []
    response = client.post("/recommend", json={"user_preferences": []})
    assert response.status_code == 200
    assert response.json() == {"places": []}


def test_missing_optional_place_fields(client, backend):
    backend[0].recommend.return_value = [{"id": "1", "name": "Парк", "category": None}]
    response = client.post("/recommend", json={"user_preferences": []})
    assert response.status_code == 200
    assert response.json() == {
        "places": [{"id": "1", "name": "Парк", "category": "Без категории",
                    "metro": None, "address": None, "work_time": None}]
    }


@pytest.mark.parametrize("broken_place", [{"id": "1"}, {"id": None, "name": "Парк"}])
def test_invalid_model_output_is_not_sent_to_android(client, backend, broken_place):
    backend[0].recommend.return_value = [broken_place]
    response = client.post("/recommend", json={"user_preferences": []})
    assert response.status_code == 500
    assert response.json() == {"detail": "Не удалось сформировать рекомендации"}


@pytest.mark.parametrize("path", ["/recommend", "/clusters"])
def test_model_not_loaded(client, monkeypatch, path):
    monkeypatch.setattr(api, "model", None)
    response = (
        client.post(path, json={"user_preferences": []})
        if path == "/recommend" else client.get(path)
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "ML-модель ещё не загружена"}


def test_recommend_failure(client, backend):
    backend[0].recommend.side_effect = RuntimeError("private model details")
    response = client.post("/recommend", json={"user_preferences": []})
    assert response.status_code == 500
    assert response.json() == {"detail": "Не удалось сформировать рекомендации"}


def test_places(client, backend, place):
    response = client.get("/places")
    assert response.status_code == 200
    assert response.json() == {"places": [place]}
    assert backend[1].call_count == 2


def test_metro_stations(client, backend):
    response = client.get("/metro-stations")
    assert response.status_code == 200
    assert response.json() == {
        "stations": [{"name": "Невский проспект", "lat": 59.935, "lon": 30.328}]
    }
    backend[2].assert_called_once_with()


@pytest.mark.parametrize("path,index,key", [
    ("/places", 1, "places"), ("/metro-stations", 2, "stations"),
])
def test_empty_database_results(client, backend, path, index, key):
    backend[index].return_value = []
    response = client.get(path)
    assert response.status_code == 200
    assert response.json() == {key: []}


@pytest.mark.parametrize("path,index", [("/places", 1), ("/metro-stations", 2)])
def test_database_failure(client, backend, path, index):
    backend[index].side_effect = RuntimeError("private database details")
    response = client.get(path)
    assert response.status_code == 503
    assert response.json() == {"detail": "База данных недоступна"}


def test_clusters_contract(client, backend, place):
    response = client.get("/clusters")
    assert response.status_code == 200
    public_place = {key: value for key, value in place.items() if not key.startswith("_")}
    assert response.json() == {
        "clusters": [{"id": 1, "key": "culture", "name": "Культура и музеи",
                      "tags": ["Культура"], "places": [public_place]}]
    }
    assert "_idx" in place
    backend[0].build_clusters.assert_called_once_with()


def test_empty_clusters(client, backend):
    backend[0].build_clusters.return_value = []
    response = client.get("/clusters")
    assert response.status_code == 200
    assert response.json() == {"clusters": []}


def test_cluster_failure(client, backend):
    backend[0].build_clusters.side_effect = RuntimeError("private model details")
    response = client.get("/clusters")
    assert response.status_code == 500
    assert response.json() == {"detail": "Не удалось загрузить категории"}


def test_reload_replaces_model(client, backend, place):
    replacement = Mock()
    replacement.places = [place, {**place, "id": "museum-2"}]
    replacement.recommend.return_value = []
    backend[3].return_value = replacement
    response = client.post("/reload-model", headers={"Authorization": "Bearer test-reload-token"})
    assert response.status_code == 200
    assert response.json()["places_count"] == 2
    assert response.json()["status"] == "success"
    backend[3].assert_called_with([place])
    assert api.model is replacement
    assert client.post("/recommend", json={"user_preferences": []}).json() == {"places": []}
    replacement.recommend.assert_called_once()
    backend[0].recommend.assert_not_called()


@pytest.mark.parametrize("failure,status", [("empty", 400), ("database", 503), ("model", 500)])
def test_failed_reload_preserves_model(client, backend, failure, status):
    old_model, places, _, factory = backend
    factory.reset_mock()
    if failure == "empty":
        places.return_value = []
    elif failure == "database":
        places.side_effect = RuntimeError("private database details")
    else:
        factory.side_effect = RuntimeError("private model details")
    response = client.post("/reload-model", headers={"Authorization": "Bearer test-reload-token"})
    assert response.status_code == status
    assert "private" not in response.text
    assert api.model is old_model
    assert client.post("/recommend", json={"user_preferences": []}).status_code == 200
    old_model.recommend.assert_called_once()
    if failure != "model":
        factory.assert_not_called()


def test_wrong_method(client, backend):
    response = client.get("/recommend")
    assert response.status_code == 405
    backend[0].recommend.assert_not_called()

@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token", "Basic dGVzdA==", "Bearer"])
def test_reload_requires_token(client, backend, authorization):
    backend[1].reset_mock()
    backend[3].reset_mock()
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.post("/reload-model", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    backend[1].assert_not_called()
    backend[3].assert_not_called()


def test_reload_disabled_without_configured_token(client, backend, monkeypatch):
    monkeypatch.setattr(api, "RELOAD_MODEL_TOKEN", "")
    backend[1].reset_mock()
    backend[3].reset_mock()
    response = client.post("/reload-model", headers={"Authorization": "Bearer test-reload-token"})
    assert response.status_code == 503
    backend[1].assert_not_called()
    backend[3].assert_not_called()


def test_parallel_reload_is_rejected_and_recommendations_remain_available(client, backend, place):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    started = Event()
    finish = Event()
    replacement = Mock()
    replacement.places = [place]

    def build(places):
        started.set()
        assert finish.wait(timeout=10)
        return replacement

    backend[3].side_effect = build
    headers = {"Authorization": "Bearer test-reload-token"}
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, "/reload-model", headers=headers)
        try:
            assert started.wait(timeout=10)
            response = client.post("/reload-model", headers=headers)
            assert response.status_code == 409
            assert api.model is backend[0]
            assert client.post("/recommend", json={"user_preferences": []}).status_code == 200
            assert backend[1].call_count == 2
        finally:
            finish.set()
        assert pending.result(timeout=10).status_code == 200
    assert api.model is replacement
    assert client.post("/reload-model", headers=headers).status_code == 200


@pytest.mark.parametrize("failure", ["database", "empty", "model"])
def test_failed_reload_releases_lock(client, backend, failure):
    if failure == "database":
        backend[1].side_effect = RuntimeError("database unavailable")
    elif failure == "empty":
        backend[1].return_value = []
    else:
        backend[3].side_effect = RuntimeError("model unavailable")
    headers = {"Authorization": "Bearer test-reload-token"}
    response = client.post("/reload-model", headers=headers)
    assert response.status_code in (400, 500, 503)
    backend[1].side_effect = None
    backend[1].return_value = backend[0].places
    backend[3].side_effect = None
    assert client.post("/reload-model", headers=headers).status_code == 200
