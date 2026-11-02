import os
import json
import pytest
from ml.model import PlacesRecommender
from utils.geo_utils import distance


def load_mock_places():
    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, "mock_places.json") 
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    
def load_cases_from_json():
    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, "test_cases.json") 
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def recommender():
    places = load_mock_places() 
    
    for p in places:
        coords = p.get("coords")
        if isinstance(coords, dict) and "lat" in coords and "lon" in coords:
            p["lat"] = coords["lat"]
            p["lon"] = coords["lon"]
        else:
            p["lat"] = None
            p["lon"] = None
            
    return PlacesRecommender(places)


def test_recommendation_compactness(recommender):
    
    user_loc = {"lat": 59.94, "lon": 30.33} 
    res = recommender.recommend(user_preferences=["история", "музей"], user_location=user_loc, top_k=3)
    
    if len(res) < 2:
        return

    total_dist = 0
    count = 0
    for i in range(len(res)):
        for j in range(i + 1, len(res)):
            p1, p2 = res[i], res[j]
            if p1.get("lat") and p2.get("lat"):
                d = distance(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
                total_dist += d
                count += 1
    
    if count > 0:
        avg_dist = total_dist / count
        assert avg_dist < 3.0, f"Результаты слишком разбросаны: среднее расстояние {avg_dist:.2f} км"


def test_global_hit_rate_threshold(recommender):
    cases = load_cases_from_json()
    if not cases:
        pytest.skip("Файл all.places.json пуст или отсутствует")
        
    hits = 0
    for case in cases:
        prefs = case["prefs"]
        loc = case.get("user_location", None)
        expected_ids = [item["id"].replace(".html", "") for item in case["expected"]]
        
        recommendations = recommender.recommend(user_preferences=prefs, user_location=loc, top_k=3)
        result_ids = [r.get("id", "").replace(".html", "") for r in recommendations]
        
        if any(exp in result_ids for exp in expected_ids):
            hits += 1
            
    hit_rate = (hits / len(cases)) * 100
    assert hit_rate >= 80.0, f"ошибка текущий Hit Rate@3: {hit_rate:.1f}%"


def test_handling_missing_coordinates(recommender):
    try:
        places = load_mock_places()
        res = recommender.recommend(user_preferences=["история"], top_k=len(places))
        assert len(res) > 0
        returned_ids = [item["id"].replace(".html", "") for item in res]
        
        assert "peterburg_gatchina-bashnya-ekaterinverder" in returned_ids
    except Exception as e:
        pytest.fail(f" Ошибка: {e}")


def test_geo_filtering_gatchina_vs_center(recommender):
    user_in_gatchina = {"lat": 59.567, "lon": 30.105}
    res = recommender.recommend(user_preferences=["парк"], user_location=user_in_gatchina, top_k=3)
    assert "gatchina" in res[0]["id"], f"Ошибка. Первый: {res[0]['name']}"


def test_deduplication_logic(recommender):
    places = load_mock_places()
    duplicated_list = places + places
    cleaned_list = recommender.unique_results(duplicated_list)
    assert len(cleaned_list) == len(places)


def test_clustering_with_corrupted_data(recommender):
    try:
        clusters = recommender.build_clusters()
        assert isinstance(clusters, list)
    except Exception as e:
        pytest.fail(f" обработка пустых координат: {e}")


def test_diversification_limits(recommender):
    heavy_religion_list = [
        {"name": "Храм 1", "address": "Адр 1", "category": "Религия"},
        {"name": "Храм 2", "address": "Адр 2", "category": "Религия"},
        {"name": "Храм 3", "address": "Адр 3", "category": "Религия"},
        {"name": "Кафе 1", "address": "Адр 4", "category": "Еда"}
    ]
    diversified = recommender.diversify_with_route(heavy_religion_list, max_k=4)
    religion_count = sum(1 for r in diversified if r.get("category") == "Религия")
    assert religion_count <= 2, f"Найдено {religion_count} объектов категории 'Религия'"


def test_geo_distance_scoring_impact(recommender):
    near_isaak = {"lat": 59.934, "lon": 30.307}
    res = recommender.recommend(user_preferences=["религия"], user_location=near_isaak, top_k=2)
    assert res[0]["id"] == "peterburg_isaakievskiy-sobor", \
        f"Гео-позиция, первым стал: {res[0]['name']}"


def test_clustering_structures(recommender):
    clusters = recommender.build_clusters()
    assert isinstance(clusters, list), "Результат - список"
    
    if len(clusters) > 0:
        for cluster in clusters:
            assert "id" in cluster
            assert "name" in cluster
            assert "tags" in cluster
            assert "places" in cluster
            assert len(cluster["places"]) > 0, f"Кластер {cluster['id']}  пустой"


def test_noise_and_empty_preferences(recommender):
    try:
        res = recommender.recommend(user_preferences=["", "интересные места", "новое на сайте"], top_k=2)
        assert len(res) > 0
    except Exception as e:
        pytest.fail(f"Ошибка при  пустых предпочтениях: {e}")



def test_cold_start_unknown_preferences(recommender):
    res = recommender.recommend(user_preferences=["киберпанк", "аниме-кафе", "космолет"], top_k=3)
    assert isinstance(res, list)
    assert len(res) > 0, "вернула пустой список на неизвестные теги"


def test_extreme_coordinates(recommender):
    south_pole = {"lat": -90.0000, "lon": 0.0000}
    try:
        res = recommender.recommend(user_preferences=["природа"], user_location=south_pole, top_k=3)
        assert len(res) > 0
    except Exception as e:
        pytest.fail(f" {e}")


def test_huge_top_k(recommender):
    places_count = len(load_mock_places())
    res = recommender.recommend(user_preferences=["история"], top_k=10000)
    assert len(res) <= places_count, "дубли"


def test_case_insensitivity(recommender):
    res_lower = recommender.recommend(user_preferences=["парк"], top_k=1)
    res_upper = recommender.recommend(user_preferences=["ПАРК"], top_k=1)
    
    if res_lower and res_upper:
        assert res_lower[0]["id"] == res_upper[0]["id"], "Регистр букв"


def test_preference_overload(recommender):
    many_prefs = ["парк", "история", "музей", "еда", "кафе", "церковь", "религия", "мост", "вид", "культура"] * 3
    try:
        res = recommender.recommend(user_preferences=many_prefs, top_k=5)
        assert len(res) == 5
    except Exception as e:
        pytest.fail(f"много тегов: {e}")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main(["-v", __file__]))