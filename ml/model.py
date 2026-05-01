from sentence_transformers import SentenceTransformer
import numpy as np


class PlacesRecommender:
    def __init__(self, places, weights=None):
        self.places = places

        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

        self.weights = weights or {
            "embedding": 1.0,
            "metro_match": 0.8,
            "distance": 0.8,
            "category": 1.0,
            "tags": 0.5,
        }

        docs = [self.build_text(p) for p in places]

        self.embeddings = self.model.encode(
            docs,
            batch_size=32,
            show_progress_bar=True,
            normalize_embeddings=True
        )

    def build_text(self, place):
        parts = []

        if place.get("name"):
            parts.append((place["name"] + " ") * 2)

        if place.get("category"):
            parts.append((place["category"] + " ") * 2)

        if place.get("tags"):
            parts.append(" ".join(place["tags"]))

        if place.get("description") and place["description"] != "—":
            parts.append(place["description"])

        if place.get("metro"):
            parts.append(place["metro"])

        return " ".join(parts)

    def compute_features(self, place, user_prefs_lower):
        features = {
            "metro_match": 0.0,
            "distance": 0.0,
            "category": 0.0,
            "tags": 0.0,
        }

        metro = (place.get("metro") or "").lower()
        if any(p in metro for p in user_prefs_lower):
            features["metro_match"] = 1.0

        dist = place.get("metro_distance_km")
        if isinstance(dist, (int, float)):
            features["distance"] = max(0, 1 - dist * 0.5)

        category = (place.get("category") or "").lower()
        if any(p in category for p in user_prefs_lower):
            features["category"] = 1.0

        tags = " ".join(place.get("tags", [])).lower()
        if any(p in tags for p in user_prefs_lower):
            features["tags"] = 1.0

        return features

    def recommend(self, user_preferences, top_k=10):
        query = self.normalize_query(user_preferences)

        query_vec = self.model.encode(
            [query],
            normalize_embeddings=True
        )[0]

        base_scores = np.dot(self.embeddings, query_vec)

        user_prefs_lower = [p.lower() for p in user_preferences]

        results = []

        for i, place in enumerate(self.places):
            score = base_scores[i] * self.weights["embedding"]

            features = self.compute_features(place, user_prefs_lower)

            for f_name, value in features.items():
                score += value * self.weights[f_name]

            results.append((i, score))

        results.sort(key=lambda x: x[1], reverse=True)

        raw = [self.places[i] for i, _ in results[:top_k * 2]]
        unique = self.unique_results(raw)

        return unique[:top_k]

    def normalize_query(self, user_preferences):
        mapping = {
            "детям": "дети семья парк развлечения безопасно",
            "музеи": "музей выставка искусство галерея культура",
            "театр": "театр спектакль сцена постановка",
            "парк": "парк прогулка природа свежий воздух",
            "еда": "ресторан кафе кухня бар еда",
            "ночь": "клуб бар ночная жизнь тусовка",
            "романтика": "романтика прогулка вид закат",
        }

        expanded = []

        for p in user_preferences:
            expanded.append(p)
            expanded.append(mapping.get(p.lower(), ""))

        return " ".join(expanded)

    def unique_results(self, results):
        seen = set()
        unique = []

        for r in results:
            key = f"{r.get('name')}_{r.get('address')}"
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique