from parser.restaurants import KudagoParser
from parser.attractions import PeterburgCenterParser
from parser.utils import save_to_json
import os
import shutil


def cleanup_previous_data():
    json_files = ['all_places.json', 'restaurants.json', 'places.json']
    image_dirs = ['kudago_images', 'places_images']
    
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

    kudago_parser = KudagoParser()
    kudago_results = kudago_parser.parse()
    all_places.extend(kudago_results)

    peterburg_parser = PeterburgCenterParser()
    peterburg_results = peterburg_parser.parse()
    all_places.extend(peterburg_results)

    if all_places:
        save_to_json(all_places, 'all_places.json')


if __name__ == "__main__":
    main()