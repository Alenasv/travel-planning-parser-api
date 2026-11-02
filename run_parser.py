from parser.attractions import PeterburgCenterParser
from parser.geoapify import GeoapifyParser
import logging
from db.database import sync_places, check_database
from collections import Counter
from utils.utils import deduplicate
from utils.normalize import finalize_place
from urllib.request import Request, urlopen
from config import (
    API_BASE_URL,
    RELOAD_MODEL_TIMEOUT,
    RELOAD_MODEL_TOKEN,
    GEOAPIFY_IMAGES_DIR,
    PETERBURG_IMAGES_DIR,
    GEOAPIFY_PER_CATEGORY,
    GEOAPIFY_AREA,
)
logger = logging.getLogger(__name__)
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
            logger.warning(
                "Отсеяно (%s): %s — %s",
                reason,
                place.get("name"),
                place.get("url")
            )

    if rejected:
        logger.info("Отсеяно всего: %s", dict(rejected))
    return result


def print_report(places):
    total = len(places)
    if not total:
        logger.warning("Нет данных")
        return

    def count(pred):
        return sum(1 for p in places if pred(p))

    logger.info("Итого мест: %s", total)
    logger.info("По источникам: %s", dict(Counter(p["source"] for p in places)))
    logger.info("По категориям: %s", dict(Counter(p["category"] for p in places)))
    logger.info(
        "С режимом работы: %s/%s, разобран в opening_hours: %s/%s",
        count(lambda p: p['work_time']),
        total,
        count(lambda p: p['opening_hours']),
        total
    )

    logger.info("С метро: %s/%s", count(lambda p: p['metro']), total)
    logger.info("С картинкой: %s/%s", count(lambda p: p['image_filename']), total)

    logger.info(
        "Откуда фото: %s",
        dict(Counter(
            p.get("image_source") or p["source"]
            for p in places if p["image_filename"]
        ))
    )
    
    logger.info("С описанием: %s/%s", count(lambda p: p['description']), total)
    logger.info("Без тегов: %s", count(lambda p: not p['tags']))

def reload_ml_model():
    if not RELOAD_MODEL_TOKEN:
        logger.error("Обновление модели пропущено: RELOAD_MODEL_TOKEN не задан")
        return False

    url = f"{API_BASE_URL}/reload-model"

    request = Request(
        url,
        data=b"",
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {RELOAD_MODEL_TOKEN}",
        }
    )

    try:
        with urlopen(request, timeout=RELOAD_MODEL_TIMEOUT) as response:
            result = response.read().decode("utf-8")
            logger.info("Ответ API: %s", result)
            return True

    except Exception as e:
        logger.exception(
            "PostgreSQL обновлена, но ML-модель не обновилась"
        )
        return False

def main():

    all_places = []


    geoapify_parser = GeoapifyParser(
        images_dir=str(GEOAPIFY_IMAGES_DIR),
        per_category=GEOAPIFY_PER_CATEGORY,
        area=GEOAPIFY_AREA
    )

    all_places.extend(geoapify_parser.parse())

    peterburg_parser = PeterburgCenterParser(
        images_dir=str(PETERBURG_IMAGES_DIR)
    )
    peterburg_results = peterburg_parser.parse()
    all_places.extend(peterburg_results)

    all_places = finalize_all(all_places)

    all_places = deduplicate(all_places)
    print_report(all_places)
    if all_places:
        sync_places(all_places)
        reload_ml_model()
    else:
        raise RuntimeError("Парсер не собрал ни одного места. БД не изменена")


if __name__ == "__main__":
    main()
    check_database()