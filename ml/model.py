from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.cluster import KMeans


class PlacesRecommender:
    def __init__(self, places, weights=None):
        self.places = places
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

        self.w = weights or {
            "embedding": 0.6,
            "category": 1.5,
            "metro": 1.0,
            "distance": 0.8,
            "tags": 0.6,
        }

        texts = [self.build_text(p) for p in places]

        self.embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=True
        )
        
        self.num_clusters = min(15, max(5, int(len(self.places) ** 0.5)))

        self.kmeans = KMeans(
            n_clusters=self.num_clusters,
            random_state=42,
            n_init=10
        )

        self.cluster_ids = self.kmeans.fit_predict(self.embeddings)

    def build_text(self, place):
        parts = []

        if place.get("name"):
            parts.append(place["name"])

        if place.get("category"):
            parts.append(place["category"])

        if place.get("tags"):
            parts.append(" ".join(place["tags"]))

        if place.get("description") and place["description"] != "—":
            parts.append(place["description"])

        if place.get("metro"):
            parts.append(place["metro"])

        return " ".join(parts)

    def normalize_query(self, prefs):
        mapping = {
            "музеи": "музей выставка искусство культура галерея",
            "адмиралтейская": "центр город невский исторический",
            "парк": "парк природа прогулка",
            "еда": "ресторан кафе кухня",
        }

        expanded = []
        for p in prefs:
            expanded.append(p)
            expanded.append(mapping.get(p.lower(), ""))

        return " ".join(expanded)

    def recommend(self, user_preferences, top_k=10):

        query = self.normalize_query(user_preferences)
        query_vec = self.model.encode([query], normalize_embeddings=True)[0]

        user_prefs = [p.lower() for p in user_preferences]

        results = []

        for i, place in enumerate(self.places):

            emb_score = float(np.dot(self.embeddings[i], query_vec))

            category = (place.get("category") or "").lower()
            metro = (place.get("metro") or "").lower()
            tags = " ".join(place.get("tags", [])).lower()
            dist = place.get("metro_distance_km")

            score = emb_score  

            if any(p in category for p in user_prefs):
                score += 0.25

            if any(p in metro for p in user_prefs):
                score += 0.2

            if any(p in tags for p in user_prefs):
                score += 0.15

            if isinstance(dist, (int, float)):
                score -= dist * 0.05

            results.append((i, score))

        results.sort(key=lambda x: x[1], reverse=True)

        ranked = [self.places[i] for i, _ in results[:top_k * 2]]

        return self.unique_results(ranked)[:top_k]

    def unique_results(self, results):
        seen = set()
        out = []

        for r in results:
            key = (r.get("name"), r.get("address"))
            if key not in seen:
                seen.add(key)
                out.append(r)

        return out
    
    def build_clusters(self):
        clusters = {}

        for idx, place in enumerate(self.places):
            cid = int(self.cluster_ids[idx])

            if cid not in clusters:
                clusters[cid] = {
                    "id": cid,
                    "name": "",
                    "places": []
                }

            clusters[cid]["places"].append(place)

        for cluster in clusters.values():
            cluster["name"] = self.get_cluster_name(cluster["places"])

        return list(clusters.values())
    
    def get_cluster_name(self, places):
        tags = []

        for p in places:
            tags.extend(p.get("tags", []))
            if p.get("category"):
                tags.append(p["category"])

        if not tags:
            return "Разное"

        # берём самые частые
        from collections import Counter
        return Counter(tags).most_common(1)[0][0]