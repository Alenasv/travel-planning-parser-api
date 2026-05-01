import json
import random
from ml.model import PlacesRecommender


def load_places(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    places = load_places("data/all_places.json")

    model = PlacesRecommender(places)

    user_preferences = ["адмиралтейская", "музеи"]
    top_k = random.randint(5, 15)

    recs = model.recommend(user_preferences, top_k=top_k)

    print(f"{len(recs)} мест\n")

    for r in recs:
        print(f"{r['name']} | {r['category']}")