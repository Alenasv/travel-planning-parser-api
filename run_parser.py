from parser.restaurants import KudagoParser
from parser.attractions import PeterburgCenterParser
from parser.utils import save_to_json
import os
import shutil
from db.database import insert_places

def cleanup_previous_data():
    json_files = ['data/all_places.json', 'data/restaurants.json', 'data/places.json']
    image_dirs = ['data/kudago_images', 'data/places_images']
    
    deleted_files = 0
    for json_file in json_files:
        if os.path.exists(json_file):
            try:
                os.remove(json_file)
                deleted_files += 1
            except Exception as e:
                print(f"Не удалось удалить {json_file}: {e}")
    
    deleted_dirs = 0
    for image_dir in image_dirs:
        if os.path.exists(image_dir):
            try:
                shutil.rmtree(image_dir)
                deleted_dirs += 1
            except Exception as e:
                print(f"Не удалось удалить {image_dir}: {e}")

def deduplicate(data):
    seen = {}

    for item in data:
        key = item.get("id")

        if key and key not in seen:
            seen[key] = item

    return list(seen.values())

def main():

    cleanup_previous_data()
    
    all_places = []

    kudago_parser = KudagoParser(location="spb")
    kudago_results = kudago_parser.parse()
    all_places.extend(kudago_results)

    peterburg_parser = PeterburgCenterParser(images_dir='data/places_images')
    peterburg_results = peterburg_parser.parse()
    all_places.extend(peterburg_results)

    for item in all_places:
        item["tags"] = item.get("tags") or []
        item["coords"] = item.get("coords") or {}


    all_places = deduplicate(all_places)

    if all_places:
        save_to_json(all_places, 'data/all_places.json')

        insert_places(all_places)


if __name__ == "__main__":
    main()