from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.cluster import KMeans
from collections import Counter
from preference_profile import CORE_PREFERENCES,NOISE_TAGS

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
        category = place.get("category", "")
        tags = " ".join(place.get("tags", []))
        name = place.get("name", "")
        desc = place.get("description", "")

        return f"""
    CATEGORY: {category}
    NAME: {name}
    TAGS: {tags}
    DESCRIPTION: {desc}
    """

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

        prefs = self.normalize_preferences(user_preferences)

        results = []

        for i, place in enumerate(self.places):

            emb_score = float(np.dot(self.embeddings[i], query_vec))

            category_score = self.score_category_boost(place, prefs)

            tags = " ".join(place.get("tags", [])).lower()

            tag_score = sum(
                0.1 for p in prefs if p in tags
            )

            score = emb_score + category_score + tag_score

            results.append((i, score))

        results.sort(key=lambda x: x[1], reverse=True)

        ranked = [self.places[i] for i, _ in results[:top_k * 3]]

        unique = self.unique_results(ranked)

        return self.diversify(unique, top_k)

    def unique_results(self, results):
        seen = set()
        out = []

        for r in results:
            key = (r.get("name"), r.get("address"))
            if key not in seen:
                seen.add(key)
                out.append(r)

        return out
    
    def score_category_boost(self, place, prefs):
        category = (place.get("category") or "").lower()

        score = 0.0

        for group, data in CORE_PREFERENCES.items():
            if any(k in category for k in data["keywords"]):
                if group in prefs:
                    score += data["boost"]

        return score
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

        return Counter(tags).most_common(1)[0][0]
    
    def diversify(self, results, max_k=10):

        selected = []
        category_count = {}

        for r in results:

            cat = (r.get("category") or "unknown").lower()

            count = category_count.get(cat, 0)

            if count >= 2:
                continue

            selected.append(r)
            category_count[cat] = count + 1

            if len(selected) >= max_k:
                break

        return selected
    
    def normalize_preferences(self, prefs):
        result = set()

        for p in prefs:
            p_low = p.lower()

            result.add(p_low)

            for group, data in CORE_PREFERENCES.items():
                if any(k in p_low for k in data["keywords"]):
                    result.add(group)
                    result.update(data["keywords"])

        return list(result)
        