from parser.attractions import PeterburgCenterParser
from parser.geoapify import GeoapifyParser
from utils.utils import save_to_json
import os
import shutil
from db.database import insert_places
from collections import Counter
from utils.utils import deduplicate
from utils.normalize import finalize_place


def finalize_all(places):
    result = []
    rejected = Counter()

    for place in places:
        if not place:
            continue
        final, reason = finalize_place(place)
        if final:
            result.append(final)
        else:
            rejected[reason] += 1
            print(f"Отсеяно ({reason}): {place.get('name')} — {place.get('url')}")

    if rejected:
        print("Отсеяно всего:", dict(rejected))
    return result


def print_report(places):
    total = len(places)
    if not total:
        print("Нет данных")
        return

    def count(pred):
        return sum(1 for p in places if pred(p))

    print(f"\nИтого мест: {total}")
    print("По источникам:", dict(Counter(p["source"] for p in places)))
    print("По категориям:", dict(Counter(p["category"] for p in places)))
    print(f"С режимом работы: {count(lambda p: p['work_time'])}/{total}, "
          f"разобран в opening_hours: {count(lambda p: p['opening_hours'])}/{total}")
    print(f"С метро: {count(lambda p: p['metro'])}/{total}")
    print(f"С картинкой: {count(lambda p: p['image_filename'])}/{total}")
    print("Откуда фото:", dict(Counter(p.get("image_source") or p["source"]
                                       for p in places if p["image_filename"])))
    no_image = [p["name"] for p in places if not p["image_filename"]]
    if no_image:
        print("Без фото:", ", ".join(no_image))
    print(f"С описанием: {count(lambda p: p['description'])}/{total}")
    print(f"Без тегов: {count(lambda p: not p['tags'])}")

def cleanup_previous_data():
    json_files = ['data/all_places.json', 'data/places.json', 'data/geoapify_places.json']
    image_dirs = ['data/places_images', 'data/geoapify_images']
    
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


def main():

    cleanup_previous_data()
    
    all_places = []


    geoapify_parser = GeoapifyParser(images_dir='data/geoapify_images', per_category=2, area="center")
    all_places.extend(geoapify_parser.parse())
    

    peterburg_parser = PeterburgCenterParser(images_dir='data/places_images')
    peterburg_results = peterburg_parser.parse()
    all_places.extend(peterburg_results)

    all_places = finalize_all(all_places)

    all_places = deduplicate(all_places)
    print_report(all_places)
    if all_places:
        save_to_json(all_places, 'data/all_places.json')

        insert_places(all_places)


if __name__ == "__main__":
    main()