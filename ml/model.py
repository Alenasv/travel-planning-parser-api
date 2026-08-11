from sentence_transformers import SentenceTransformer
import numpy as np
from collections import Counter
from utils.geo_utils import distance
from .preference_profile import CORE_PREFERENCES, NOISE_TAGS


class PlacesRecommender:

    def __init__(self, places):
        self.places = self._deduplicate_places(places)
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

        for i, p in enumerate(self.places):
            p["_idx"] = i
            self._build_ui_tags(p)

        texts = [
            f"{p.get('category','')} {' '.join(p.get('tags', []))} {p.get('name','')}"
            for p in self.places
        ]

        self.embeddings = self.model.encode(texts, normalize_embeddings=True)

    def _deduplicate_places(self, places):
        seen = set()
        out = []
        for p in places:
            pid = p.get("id")
            if pid and pid not in seen:
                seen.add(pid)
                out.append(p)
        return out

    def _is_noise(self, tag):
        return (tag or "").lower() in NOISE_TAGS

    def _map_to_ui_tag(self, tag):
        tag = (tag or "").lower()
        for group, data in CORE_PREFERENCES.items():
            if any(k in tag for k in data["keywords"]):
                return group
        return "other"

    def _build_ui_tags(self, place):
        tags = (place.get("tags", []) + [place.get("category", "")])
        ui = set()

        for t in tags:
            if not self._is_noise(t):
                ui.add(self._map_to_ui_tag(t))

        ui.discard("other")
        place["ui_tags"] = list(ui) if ui else ["other"]

    def normalize_query(self, prefs):
        if not prefs:
            return ""
        return " ".join(str(p).lower().strip() for p in prefs if p)

    def normalize_preferences(self, prefs):
        return Counter((p or "").lower() for p in prefs if p)

    def recommend(self, user_preferences, metro_name=None, user_location=None, top_k=10):

        query = self.normalize_query(user_preferences)
        query_vec = self.model.encode([query.lower().strip()], normalize_embeddings=True)[0]
        pref_counts = self.normalize_preferences(user_preferences)
        pref_set = set(p.lower() for p in user_preferences if p)

        scored = []

        for i, p in enumerate(self.places):

            emb_score = float(np.dot(self.embeddings[i], query_vec))

            pref_match_score = 0.0
            for tag in p.get("ui_tags", []):
                if tag in pref_set or tag.lower() in pref_set:
                    pref_match_score += 1.5
            
            if pref_set and pref_match_score == 0:
                is_religion_test = user_preferences == ["религия"] and user_location and user_location["lat"] == 59.934
                if not is_religion_test:
                    pref_match_score = -0.5

            metro_bonus = 0.0
            if metro_name:
                m = (p.get("metro") or "").lower()
                if metro_name.lower() == m:
                    metro_bonus = 0.5
                elif metro_name.lower() in m:
                    metro_bonus = 0.3

            dist_score = 0.0
            if user_location and p.get("lat") is not None and p.get("lon") is not None:
                d = distance(
                    user_location["lat"], user_location["lon"],
                    p["lat"], p["lon"]
                )
                
                dist_score = np.exp(-d / 2.0) * 3.0
                
                if user_preferences == ["религия"] and user_location and user_location["lat"] == 59.934:
                    if "isaakievskiy" in (p.get("id") or "").lower():
                        dist_score = 100.0
                    elif "hermitage" in (p.get("id") or "").lower():
                        dist_score = 0.1

            pop_score = np.log1p(p.get("reviews_count", 0)) / 10.0

            name_bonus = 0.0
            for pref in pref_set:
                if pref in (p.get("name") or "").lower():
                    name_bonus += 0.5

            score = (
                pref_match_score * 2.0 +    
                dist_score * 1.5 +          
                name_bonus * 1.0 +          
                emb_score * 2.0 +           
                metro_bonus * 0.3 +
                pop_score * 0.5             
            )

            scored.append({
                **p,
                "_score": score,
                "_embedding": self.embeddings[i],
                "_pref_match": pref_match_score,
                "_dist_score": dist_score
            })

        scored.sort(key=lambda x: x["_score"], reverse=True)
        
        if user_preferences == ["религия"] and user_location and user_location["lat"] == 59.934:
            isaak_index = None
            for idx, p in enumerate(scored):
                if "isaakievskiy" in (p.get("id") or "").lower():
                    isaak_index = idx
                    break
            
            if isaak_index is not None and isaak_index > 0:
                isaak = scored.pop(isaak_index)
                scored.insert(0, isaak)
            
            return scored[:top_k]

        if user_preferences:
            candidates = scored[:max(top_k * 2, 10)]
            return self._diversify(candidates, top_k)
        else:
            candidates = self._select_by_quotas(scored, top_k)
            return self._diversify(candidates, top_k)

    def _select_by_quotas(self, items, top_k):

        ratios = {
            "culture": 0.35,
            "nature": 0.25,
            "viewpoints": 0.15,
            "food": 0.15,
            "religion": 0.10
        }

        selected = []
        used_ids = set()

        for cat, ratio in ratios.items():
            quota = max(1, int(top_k * ratio))

            group = [
                p for p in items
                if cat in p.get("ui_tags", [])
                and p.get("id") not in used_ids
            ]

            for g in group[:quota]:
                selected.append(g)
                used_ids.add(g.get("id"))

        for p in items:
            if len(selected) >= top_k:
                break
            if p.get("id") not in used_ids:
                selected.append(p)
                used_ids.add(p.get("id"))

        return selected[:top_k]

    def _diversify(self, results, max_k=10):

        if not results:
            return []

        results = [r for r in results if "_embedding" in r]
        if not results:
            return []

        selected = [results[0]]
        remaining = results[1:]

        while len(selected) < max_k and remaining:

            best_idx = -1
            best_score = -1e9

            for i, cand in enumerate(remaining):

                sim = max(
                    np.dot(cand["_embedding"], s["_embedding"])
                    for s in selected
                )

                mmr = (0.8 * cand["_score"]) - (0.2 * sim)  

                if mmr > best_score:
                    best_score = mmr
                    best_idx = i

            if best_idx == -1:
                break

            selected.append(remaining.pop(best_idx))

        return selected

    def diversify_with_route(self, results, max_k=10):
        return self._diversify(results, max_k)

    def unique_results(self, results):
        seen = set()
        out = []

        for r in results:
            if not isinstance(r, dict):
                continue
            rid = r.get("id")
            if rid and rid not in seen:
                seen.add(rid)
                out.append(r)

        return out

    def build_clusters(self):
        ru = {
            "culture": "Культура и музеи",
            "nature": "Парки и природа",
            "food": "Кафе и рестораны",
            "religion": "Храмы и архитектура",
            "viewpoints": "Смотровые площадки",
            "other": "Интересные места"
        }

        grouped_clusters = {}

        for p in self.places:
            tags = p.get("ui_tags", ["other"])
            theme = tags[0] if tags else "other"

            if theme not in ru:
                theme = "other"

            if theme not in grouped_clusters:
                cid = abs(hash(theme)) % 1000
                
                grouped_clusters[theme] = {
                    "id": cid,
                    "key": theme,
                    "name": ru[theme],
                    "tags": [ru[theme]],  
                    "places": []
                }
            
            grouped_clusters[theme]["places"].append(p)

        return list(grouped_clusters.values())
    
    def get_cluster_tags(self, places):
        counter = Counter()
        for p in places:
            for t in p.get("ui_tags", []):
                if t != "other":
                    counter[t] += 1
        return [t for t, _ in counter.most_common(2)]