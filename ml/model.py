from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

class PlacesRecommender:
    def __init__(self, places):
        self.places = places

        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

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
            parts.append(place["name"])

        if place.get("category"):
            parts.append(place["category"])

        if place.get("tags"):
            parts.extend(place["tags"])

        if place.get("description") and place["description"] != "—":
            parts.append(place["description"])

        if place.get("metro"):
            parts.append(place["metro"])

        return " ".join(parts)

    def recommend(self, user_preferences, top_k=10):

        query = self.normalize_query(user_preferences)

        query_vec = self.model.encode(
            [query],
            normalize_embeddings=True
        )[0]

        scores = np.dot(self.embeddings, query_vec)

        results = []

        for i, place in enumerate(self.places):
            score = float(scores[i])

            metro = place.get("metro")
            if metro:
                for p in user_preferences:
                    if p.lower() in metro.lower():
                        score += 0.5

            dist = place.get("metro_distance_km")
            if dist is not None:
                score += max(0, 0.6 - dist * 0.3)

            if place.get("category"):
                for p in user_preferences:
                    if p.lower() in place["category"].lower():
                        score += 0.7

            if place.get("tags"):
                tag_str = " ".join(place["tags"])
                for p in user_preferences:
                    if p.lower() in tag_str.lower():
                        score += 0.4

            results.append((i, score))

        results.sort(key=lambda x: x[1], reverse=True)

        return [self.places[i] for i, _ in results[:top_k]]
    
    def normalize_query(self, user_preferences):
        mapping = {
            "детям": "семейный отдых дети парк развлечения",
            "музеи": "музей выставка искусство культура",
            "театр": "театр спектакль постановка",
            "парк": "парк прогулка природа",
            "еда": "ресторан кафе кухня"
        }

        expanded = []

        for p in user_preferences:
            expanded.append(p)
            expanded.append(mapping.get(p.lower(), ""))

        return " ".join(expanded)