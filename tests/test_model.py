import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import api
from ml import model as model_module
from ml.model import PlacesRecommender


@pytest.fixture
def make_recommender(monkeypatch):
    def create(places):
        encoder = Mock()
        encoder.encode.side_effect = lambda texts, **kwargs: np.tile([1.0, 0.0], (len(texts), 1))
        monkeypatch.setattr(model_module, "SentenceTransformer", Mock(return_value=encoder))
        return PlacesRecommender(copy.deepcopy(places))

    return create


@pytest.fixture
def places():
    return [
        {"id": "food-1", "name": "Точка A", "category": "Еда", "tags": ["кафе"]},
        {"id": "culture-1", "name": "Точка B", "category": "Культура", "tags": ["музей"]},
        {"id": "nature-1", "name": "Точка C", "category": "Природа", "tags": ["парк"]},
        {"id": "religion-1", "name": "Точка D", "category": "Религия", "tags": ["храм", "архитектура"]},
    ]


def cluster_membership(recommender):
    return [
        (cluster["id"], cluster["key"], [place["id"] for place in cluster["places"]])
        for cluster in recommender.build_clusters()
    ]


def test_cluster_ids_and_order(make_recommender, places):
    recommender = make_recommender(places)
    assert cluster_membership(recommender) == [
        (1, "culture", ["culture-1"]),
        (2, "nature", ["nature-1"]),
        (3, "food", ["food-1"]),
        (4, "religion", ["religion-1"]),
    ]


def test_cluster_membership_does_not_depend_on_input_order(make_recommender, places):
    places.append({"id": "culture-2", "category": "История", "tags": ["вид", "храм"]})
    first = make_recommender(places)
    reversed_places = copy.deepcopy(list(reversed(places)))
    for place in reversed_places:
        place["tags"].reverse()
    second = make_recommender(reversed_places)
    assert cluster_membership(first) == cluster_membership(second)
    assert first.places[-1]["ui_tags"] == ["culture", "religion", "viewpoints"]
    assert second.places[0]["ui_tags"] == ["culture", "religion", "viewpoints"]


def test_category_selects_primary_cluster(make_recommender):
    recommender = make_recommender([
        {"id": "1", "category": "Религия", "tags": ["история", "архитектура", "парк"]},
    ])
    assert cluster_membership(recommender) == [(4, "religion", ["1"])]


def test_unknown_category_uses_deterministic_tag_priority(make_recommender):
    recommender = make_recommender([
        {"id": "1", "category": "Достопримечательность", "tags": ["храм", "музей"]},
    ])
    assert cluster_membership(recommender) == [(1, "culture", ["1"])]


def test_all_supported_categories_have_distinct_clusters(make_recommender):
    categories = [
        "Культура", "Природа", "Еда", "Религия", "Видовые места",
        "Развлечения", "Активный отдых", "Семья", "Неизвестная категория",
    ]
    recommender = make_recommender([
        {"id": str(index), "category": category, "tags": []}
        for index, category in enumerate(categories, start=1)
    ])
    assert cluster_membership(recommender) == [
        (1, "culture", ["1"]), (2, "nature", ["2"]), (3, "food", ["3"]),
        (4, "religion", ["4"]), (5, "viewpoints", ["5"]),
        (6, "entertainment", ["6"]), (7, "active", ["7"]),
        (8, "family", ["8"]), (9, "other", ["9"]),
    ]


@pytest.mark.parametrize("place", [
    {"id": "1"}, {"id": "1", "category": None, "tags": None},
    {"id": "1", "category": "", "tags": ["", None, "новое на сайте"]},
])
def test_missing_metadata_goes_to_other_cluster(make_recommender, place):
    recommender = make_recommender([place])
    assert cluster_membership(recommender) == [(9, "other", ["1"])]


def test_every_place_belongs_to_one_cluster(make_recommender, places):
    recommender = make_recommender(places + [places[0]])
    ids = [place["id"] for cluster in recommender.build_clusters() for place in cluster["places"]]
    assert sorted(ids) == ["culture-1", "food-1", "nature-1", "religion-1"]


def test_empty_catalog_has_no_clusters(make_recommender):
    assert make_recommender([]).build_clusters() == []


@pytest.mark.parametrize("preference,key", [
    ("culture", "culture"), ("Культура", "culture"), ("Культура и музеи", "culture"),
    (" музей ", "culture"), ("ИСТОРИЯ", "culture"),
    ("nature", "nature"), ("Парки и природа", "nature"),
    ("food", "food"), ("Кафе и рестораны", "food"),
    ("religion", "religion"), ("Храмы и архитектура", "religion"),
    ("Смотровые площадки", "viewpoints"), ("Развлечения", "entertainment"),
    ("Активный отдых", "active"), ("Семья", "family"),
    ("парк развлечений", "entertainment"),
])
def test_normalizes_preference_aliases(make_recommender, preference, key):
    recommender = make_recommender([])
    assert recommender.normalize_preferences([preference]) == {key: 1}


@pytest.mark.parametrize("preferences", [
    ["culture"], ["Культура"], ["Культура и музеи"], [" КУЛЬТУРА И МУЗЕИ "],
])
def test_category_aliases_produce_same_semantic_query(make_recommender, preferences):
    recommender = make_recommender([])
    assert recommender.normalize_query(preferences) == "культура и музеи"


@pytest.mark.parametrize("preference,expected_id", [
    ("Культура и музеи", "culture-1"), ("Храмы и архитектура", "religion-1"),
    ("Парки и природа", "nature-1"), ("Кафе и рестораны", "food-1"),
])
def test_android_preferences_affect_ranking(make_recommender, places, preference, expected_id):
    recommender = make_recommender(places)
    result = recommender.recommend([preference], top_k=4)
    assert len(result) == 4
    assert result[0]["id"] == expected_id
    assert result[0]["_pref_match"] == 1.5
    expected_matches = (
        {"culture-1", "religion-1"} if expected_id == "culture-1" else {expected_id}
    )
    assert {place["id"] for place in result if place["_pref_match"] == 1.5} == expected_matches
    assert all(place["_pref_match"] == -0.5 for place in result if place["id"] not in expected_matches)


def test_duplicate_preferences_do_not_inflate_scores(make_recommender, places):
    recommender = make_recommender(places)
    single = recommender.recommend(["culture"], top_k=4)
    repeated = recommender.recommend(["culture"] * 5, top_k=4)
    assert [(p["id"], p["_score"]) for p in single] == [(p["id"], p["_score"]) for p in repeated]


def test_noise_preferences_use_cold_start(make_recommender, places):
    recommender = make_recommender(places)
    noise = recommender.recommend(["", "новое на сайте", "Интересные места"], top_k=3)
    empty = recommender.recommend([], top_k=3)
    assert [(p["id"], p["_score"]) for p in noise] == [(p["id"], p["_score"]) for p in empty]


def test_unknown_preferences_keep_semantic_text(make_recommender):
    recommender = make_recommender([])
    assert recommender.normalize_query([" Космолёт "]) == "космолёт"
    assert recommender.normalize_preferences(["Космолёт"]) == {"космолёт": 1}


def test_android_can_recommend_using_returned_cluster_names(make_recommender, places, monkeypatch):
    recommender = make_recommender(places)
    monkeypatch.setattr(api, "get_all_places", Mock(return_value=places))
    monkeypatch.setattr(api, "build_recommender", Mock(return_value=recommender))
    with TestClient(api.app) as client:
        clusters = client.get("/clusters")
        assert clusters.status_code == 200
        for cluster in clusters.json()["clusters"]:
            response = client.post("/recommend", json={
                "user_preferences": [cluster["name"]], "top_k": 1,
            })
            assert response.status_code == 200
            assert response.json()["places"][0]["id"] == cluster["places"][0]["id"]


def test_clusters_are_stable_across_hash_seeds():
    code = """
import json
from ml.model import PlacesRecommender
recommender = PlacesRecommender.__new__(PlacesRecommender)
recommender.places = [
    {"id": "2", "category": "Религия", "tags": ["история", "храм"]},
    {"id": "1", "category": "Еда", "tags": ["кафе"]},
]
for place in recommender.places:
    recommender._build_ui_tags(place)
print(json.dumps(recommender.build_clusters(), ensure_ascii=True, sort_keys=True))
"""
    results = []
    for seed in ("1", "42"):
        process = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONHASHSEED": seed, "HF_HUB_OFFLINE": "1"},
            capture_output=True,
            text=True,
            check=True,
            timeout=90,
        )
        results.append(json.loads(process.stdout))
    assert results[0] == results[1]
    assert [(cluster["id"], cluster["key"]) for cluster in results[0]] == [(3, "food"), (4, "religion")]
