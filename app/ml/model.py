from sentence_transformers import SentenceTransformer
import numpy as np
from collections import Counter
from app.utils.geo_utils import distance
from .preference_profile import CLUSTERS, CORE_PREFERENCES, NOISE_TAGS, PREFERENCE_ALIASES


class PlacesRecommender:

    def __init__(self, places):
        self.places = self._deduplicate_places(places)
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

        for i, p in enumerate(self.places):
            p["_idx"] = i
            self._build_ui_tags(p)

        texts = [
            " ".join(
                [p.get("category") or "", p.get("name") or ""]
                + [tag for tag in (p.get("tags") or []) if tag]
            )
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
        return (tag or "").strip().casefold() in NOISE_TAGS

    def _map_to_ui_tag(self, tag):
        tag = (tag or "").strip().casefold()
        if tag in PREFERENCE_ALIASES:
            return PREFERENCE_ALIASES[tag]
        matches = [
            (len(keyword), group)
            for group, data in CORE_PREFERENCES.items()
            for keyword in data["keywords"]
            if keyword in tag
        ]
        return max(matches, default=(0, "other"))[1]

    def _build_ui_tags(self, place):
        tags = (place.get("tags") or []) + [place.get("category") or ""]
        ui = {
            self._map_to_ui_tag(tag)
            for tag in tags
            if not self._is_noise(tag)
        }
        place["ui_tags"] = [key for key in CLUSTERS if key != "other" and key in ui] or ["other"]

    def normalize_query(self, prefs):
        parts = []
        for pref in prefs or []:
            value = (pref or "").strip().casefold()
            if not value or self._is_noise(value):
                continue
            key = PREFERENCE_ALIASES.get(value)
            parts.append(CLUSTERS[key]["name"].casefold() if key else value)
        return " ".join(dict.fromkeys(parts))

    def normalize_preferences(self, prefs):
        normalized = Counter()
        for pref in prefs or []:
            value = (pref or "").strip().casefold()
            if not value or self._is_noise(value):
                continue
            key = self._map_to_ui_tag(value)
            normalized[key if key != "other" else value] += 1
        return normalized

    def recommend(self, user_preferences, metro_name=None, user_location=None, top_k=10):

        query = self.normalize_query(user_preferences)
        query_vec = self.model.encode([query.lower().strip()], normalize_embeddings=True)[0]
        pref_set = set(self.normalize_preferences(user_preferences))
        name_preferences = {
            (pref or "").strip().casefold()
            for pref in user_preferences or []
            if (pref or "").strip() and not self._is_noise(pref)
        }

        scored = []

        for i, p in enumerate(self.places):

            emb_score = float(np.dot(self.embeddings[i], query_vec))

            pref_match_score = 0.0
            for tag in p.get("ui_tags", []):
                if tag in pref_set or tag.lower() in pref_set:
                    pref_match_score += 1.5
            
            if pref_set and pref_match_score == 0:
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
                
                

            name_bonus = 0.0
            for pref in name_preferences:
                if pref in (p.get("name") or "").casefold():
                    name_bonus += 0.5

            score = (
                pref_match_score * 2.0 +
                dist_score * 1.5 +
                name_bonus * 1.0 +
                emb_score * 2.0 +
                metro_bonus * 0.3
            )

            scored.append({
                **p,
                "_score": score,
                "_embedding": self.embeddings[i],
                "_pref_match": pref_match_score,
                "_dist_score": dist_score
            })

        scored.sort(key=lambda x: x["_score"], reverse=True)
        
        

        if pref_set:
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
        grouped = {key: [] for key in CLUSTERS}
        for place in self.places:
            theme = self._map_to_ui_tag(place.get("category"))
            if theme == "other":
                tags = place.get("ui_tags") or []
                theme = next(
                    (key for key in CLUSTERS if key != "other" and key in tags),
                    "other",
                )
            grouped[theme].append(place)

        return [
            {
                "id": cluster["id"],
                "key": key,
                "name": cluster["name"],
                "tags": [cluster["name"]],
                "places": sorted(grouped[key], key=lambda place: str(place["id"])),
            }
            for key, cluster in CLUSTERS.items()
            if grouped[key]
        ]

    def get_cluster_tags(self, places):
        counter = Counter()
        for p in places:
            for t in p.get("ui_tags", []):
                if t != "other":
                    counter[t] += 1
        return [t for t, _ in counter.most_common(2)]