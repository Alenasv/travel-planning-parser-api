from model import PlacesRecommender
import json

with open("data/all_places.json", "r", encoding="utf-8") as f:
    places = json.load(f)

model = PlacesRecommender(places)

prefs = ["музеи", "парк", "адмиралтейская"]

results = model.recommend(prefs, top_k=10)

for r in results:
    print("-", r["name"], "|", r["category"], "|", r.get("metro"))