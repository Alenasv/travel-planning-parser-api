def build_features(place):
    features = []

    if place.get("category"):
        features.append(place["category"])
        features.append(place["category"])

    if place.get("tags"):
        features.extend(place["tags"])

    if place.get("name"):
        features.append(place["name"])

    if place.get("description") and place["description"] != "—":
        features.append(place["description"])

    if place.get("metro"):
        features.append(place["metro"])

    return " ".join(features)
