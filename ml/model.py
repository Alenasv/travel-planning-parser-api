from sentence_transformers import SentenceTransformer
import numpy as np
import re
from sklearn.cluster import KMeans
from collections import Counter
from utils.geo_utils import distance, nearest_metro
from .preference_profile import CORE_PREFERENCES, NOISE_TAGS, UI_TAGS

class PlacesRecommender:
    def __init__(self, places, weights=None):
        self.places = [p for p in places if isinstance(p, dict) and "id" in p]
        self.places = places
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

        self.w = weights or {
            "embedding": 0.6,
            "category": 1.5,
            "metro": 1.0,
            "distance": 0.8,
            "tags": 0.6,
        }
        
        for p in self.places:
            self.build_ui_tags(p)
            
        texts = [self.build_text(p) for p in places]

        self.embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=True
        )
        
        self.num_clusters = min(8, max(1, len(self.places)))

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

        return f"CATEGORY: {category}\nNAME: {name}\nTAGS: {tags}\nDESCRIPTION: {desc}"

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

    def recommend(self, user_preferences, user_location=None, top_k=10):
       
        query = self.normalize_query(user_preferences)
        query_vec = self.model.encode([query], normalize_embeddings=True)[0]
        prefs = self.normalize_preferences(user_preferences)

        scored_places = []
        for i, place in enumerate(self.places):
            distance_score = 0.0
            metro_score = 0.0

            place_lat = place.get("lat")
            place_lon = place.get("lon")

            if user_location and place_lat is not None and place_lon is not None:
                d = distance(user_location["lat"], user_location["lon"], place_lat, place_lon)
                if d is not None:
                    distance_score = max(0, 1 - (d / 10)) 

                metro_name, metro_dist = nearest_metro(place_lat, place_lon)
                if metro_dist is not None:
                    metro_score = max(0, 1 - (metro_dist / 2))

            emb_score = float(np.dot(self.embeddings[i], query_vec)) * self.w.get("embedding", 1.0)
            category_score = self.score_category_boost(place, prefs) * self.w.get("category", 1.0)

            tags = " ".join(place.get("tags", [])).lower()
            tag_score = sum(0.1 for p in prefs if p in tags) * self.w.get("tags", 1.0)

            total_score = (
                emb_score + category_score + tag_score + 
                distance_score * self.w.get("distance", 1.0) + 
                metro_score * self.w.get("metro", 1.0)
            )
            scored_places.append({"index": i, "score": total_score})

        scored_places.sort(key=lambda x: x["score"], reverse=True)
        
        candidate_indices = [sp["index"] for sp in scored_places[:top_k * 5]]
        final_ranked = []
        
        if candidate_indices:
            first_idx = candidate_indices.pop(0)
            final_ranked.append(self.places[first_idx])
            
            while candidate_indices and len(final_ranked) < top_k:
                best_idx = -1
                best_combined_score = -1
                
                for idx in candidate_indices:
                    place = self.places[idx]
                    
                    if place.get("lat") is None or place.get("lon") is None:
                        combined_score = scored_places[idx]["score"]
                    else:
                        avg_dist_to_selected = 0
                        for selected in final_ranked:
                            d = distance(place["lat"], place["lon"], selected["lat"], selected["lon"])
                            avg_dist_to_selected += d if d is not None else 5 
                        avg_dist_to_selected /= len(final_ranked)
                        
                        proximity_bonus = max(0, 1 - (avg_dist_to_selected / 5)) 
                        combined_score = scored_places[idx]["score"] * (1 + proximity_bonus * 0.5)
                    
                    if combined_score > best_combined_score:
                        best_combined_score = combined_score
                        best_idx = idx
                
                final_ranked.append(self.places[best_idx])
                candidate_indices.remove(best_idx)

        
        unique = self.unique_results(final_ranked)
        return self.diversify(unique, top_k)

    def unique_results(self, results):
        seen = set()
        out = []
        for r in results:
            key = r.get("id") 
            if key and key not in seen:
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
                    "tags": [],
                    "places": []
                }
            clusters[cid]["places"].append(place)

        used_names = set()

        for cluster in list(clusters.values()):
            refined_tags = self.get_cluster_tags(cluster["places"])
            cluster["tags"] = refined_tags
            
            cluster_name = "Интересное"
            for tag in refined_tags:
                if tag not in used_names:
                    cluster_name = tag
                    break
            
            if cluster_name in used_names and len(refined_tags) > 1:
                combined_name = f"{refined_tags[0]} и {refined_tags[1].lower()}"
                if combined_name not in used_names:
                    cluster_name = combined_name

            if cluster_name in used_names:
                base_name = cluster_name
                counter = 2
                while f"{base_name} {counter}" in used_names:
                    counter += 1
                cluster_name = f"{base_name} {counter}"

            used_names.add(cluster_name)
            cluster["name"] = cluster_name

        return [c for c in clusters.values() if len(c["places"]) > 0]

    def get_cluster_tags(self, places):
        counter = Counter()

        ru_labels = {
            "museums": "Музеи",
            "museum": "Музеи",
            "history": "История",
            "historical": "История",
            "parks": "Парки",
            "park": "Парки",
            "nature": "Природа",
            "food": "Еда и рестораны",
            "cafe": "Кафе",
            "restaurants": "Рестораны",
            "culture": "Культура",
            "art": "Искусство",
            "theaters": "Театры",
            "theater": "Театры",
            "entertainment": "Развлечения",
            "architecture": "Архитектура",
            "attractions": "Достопримечательности",
            "sightseeing": "Достопримечательности",
            "walks": "Прогулки",
            "religion": "Религия",
            "other": "Разное"
        }

        for p in places:
            for t in p.get("tags", []):
                if not t:
                    continue
                t_low = t.lower().strip()
                if self.is_noise(t_low):
                    continue

                if t_low in UI_TAGS:
                    counter[t_low] += 1
                else:
                    mapped = self.map_to_ui_tag(t_low)
                    if mapped != "other":
                        counter[mapped.lower()] += 1
            
            cat = p.get("category", "")
            if cat:
                cat_low = cat.lower().strip()
                if not self.is_noise(cat_low):
                    if cat_low in UI_TAGS:
                        counter[cat_low] += 1
                    else:
                        mapped = self.map_to_ui_tag(cat_low)
                        if mapped != "other":
                            counter[mapped.lower()] += 1

        if not counter:
            return ["Интересное"]

        top = counter.most_common(3)
        result = []
        
        for k, _ in top:
            k_low = k.lower().strip()
            
            if k_low in ru_labels:
                result.append(ru_labels[k_low])
            elif re.search(r'[а-яА-Я]', k):
                result.append(k.capitalize())
            else:
                result.append("Разное")

        return result
    
    def map_to_ui_tag(self, tag: str):
        tag = tag.lower()
        for group, data in CORE_PREFERENCES.items():
            if any(k in tag for k in data["keywords"]):
                return group
        return "other"

    def is_noise(self, tag: str):
        return tag.lower() in NOISE_TAGS

    def build_ui_tags(self, place):
        ui_tags = set()
        for t in place.get("tags", []):
            if self.is_noise(t):
                continue
            ui = self.map_to_ui_tag(t)
            if ui != "other":
                ui_tags.add(ui)

        cat = place.get("category", "")
        ui = self.map_to_ui_tag(cat)
        if ui != "other":
            ui_tags.add(ui)

        place["ui_tags"] = list(ui_tags) if ui_tags else ["other"]
    
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
            if not p:
                continue
            p_low = p.lower().strip()
            result.add(p_low)
            for group, data in CORE_PREFERENCES.items():
                if any(k in p_low for k in data.get("keywords", [])):
                    result.add(group.lower())
                    for k in data.get("keywords", []):
                        result.add(k.lower())
        return list(result)