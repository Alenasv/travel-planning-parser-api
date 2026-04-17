import requests
import uuid
import time
import os
from parser.utils import save_to_json, download_image,map_category,clean_text

class KudagoParser:
    BASE_URL = "https://kudago.com/public-api/v1.4"
    EXCLUDE_CATEGORIES = [
        "Питомники", "Кошачий питомник", "Собачий питомник",
        "Учебные заведения", "Метро", "Стрип-клуб"
    ]

    def __init__(self, location="spb", images_dir="data/kudago_images"):
        self.location = location
        self.session = requests.Session()
        self.images_dir = images_dir
        os.makedirs(images_dir, exist_ok=True)

    def get_categories(self):
        url = f"{self.BASE_URL}/place-categories/"
        params = {"lang": "ru", "fields": "slug,name"}
        response = self.session.get(url, params=params)
        return response.json()

    def get_places_by_category(self, category_slug):
        url = f"{self.BASE_URL}/places/"
        params = {
            "location": self.location,
            "categories": category_slug,
            "page_size": 1,
            "fields": "id,title,address,coords,subway,site_url,description,tags"
        }
        response = self.session.get(url, params=params)
        data = response.json()
        return data.get("results", [])

    def get_place_details(self, place_id):
        url = f"{self.BASE_URL}/places/{place_id}/"
        params = {"lang": "ru", "expand": "images"}
        response = self.session.get(url, params=params)
        return response.json()

    def format_place(self, place, category_name):
        images = place.get("images", [])
        image_url = images[0]["image"] if images else None
        image_filename = None
        if image_url:
            image_filename = download_image(image_url, place.get("title"), self.images_dir)
            if image_filename:
                image_filename = os.path.join("kudago_images", os.path.basename(image_filename))
        mapped_category = map_category(category_name)
        return {
            "id": f"kudago_{place.get('id')}",
            "name": place.get("title"),
            "address": place.get("address") or "—",
            "coords": place.get("coords"),
            "metro": place.get("subway") or "—",
            "description": clean_text(place.get("description") or "—"),
            "tags": place.get("tags", []),  
            "category": mapped_category,
            "work_time": "-",
            "source": "kudago",
            "image_filename": image_filename or "kudago_images/default_place.jpg",
            "url": f"https://kudago.com/spb/place/{place.get('id')}/"
        }

    def parse(self):
        results = []
        categories = self.get_categories()

        for category in categories:
            slug = category["slug"]
            name = category["name"]

            if name in self.EXCLUDE_CATEGORIES:
                continue 

            try:
                places = self.get_places_by_category(slug)
                for place in places:
                    details = self.get_place_details(place["id"])
                    formatted = self.format_place(details, name)
                    results.append(formatted)

                time.sleep(0.5)
            except Exception as e:
                print(f"Ошибка категории {name}: {e}")

        return results


if __name__ == "__main__":
    parser = KudagoParser()
    results = parser.parse()
    os.makedirs("data", exist_ok=True)
    save_to_json(results, "data/all_places.json")