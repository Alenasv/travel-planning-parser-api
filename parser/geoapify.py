import os
import re
import json
import time
import hashlib
import requests
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from utils.utils import save_to_json, download_image, clean_text
from utils.geo_utils import reverse_geocode, distance

load_dotenv()

PLACES_URL = "https://api.geoapify.com/v2/places"
WIKIDATA_URL = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIPEDIA_SUMMARY_URL = "https://ru.wikipedia.org/api/rest_v1/page/summary/{title}"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API_URL = "https://ru.wikipedia.org/w/api.php"

NEARBY_PHOTO_CATEGORIES = {"Культура", "История", "Религия", "Природа"}
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
ADULT_KEYWORDS = ("стрип", "strip", "эрот", "erot", "гоу-гоу", "go-go", "зависть", "zависть")
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_contact = os.getenv("WIKIMEDIA_CONTACT")
USER_AGENT = (f"travel-planning-parser/1.0 (educational project; {_contact})" if _contact
              else "travel-planning-parser/1.0 (educational project)")
WIKI_MIN_INTERVAL = 1.0

SPB_CENTER = (30.3158, 59.9398)
SPB_RECT = "29.42,59.63,30.76,60.25"
SPB_NAME = "Санкт-Петербург"

AREAS = {
    "center": ("30.25,59.91,30.40,59.97", 2),
    "city": (SPB_RECT, 6),
}
PAGE_LIMIT = 500
MAX_SPLIT_DEPTH = 4

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, ".geoapify_cache")
CACHE_TTL_SECONDS = 7 * 24 * 3600

PLACE_TYPES = [
    ("catering.restaurant", "Еда и напитки", "Ресторан", ["ресторан", "еда"]),
    ("catering.cafe", "Еда и напитки", "Кафе", ["кафе", "еда"]),
    ("catering.bar", "Еда и напитки", "Бар", ["бар"]),
    ("catering.pub", "Еда и напитки", "Паб", ["бар", "паб"]),

    ("entertainment.cinema", "Развлечения", "Кинотеатр", ["кино", "развлечения"]),
    ("entertainment.culture.theatre", "Развлечения", "Театр", ["театр", "шоу"]),
    ("adult.nightclub", "Развлечения", "Клуб", ["клуб", "развлечения"]),
    ("entertainment.escape_game", "Развлечения", "Квест", ["квест", "игры"]),
    ("entertainment.theme_park", "Развлечения", "Парк развлечений", ["аттракционы", "парк развлечений"]),

    ("entertainment.museum", "Культура", "Музей", ["музей"]),
    ("entertainment.culture.gallery", "Культура", "Галерея", ["галерея", "искусство", "выставка"]),
    ("entertainment.culture.arts_centre", "Культура", "Арт-пространство", ["искусство", "выставка"]),

    ("tourism.sights.castle", "История", "Дворец", ["дворец", "история", "архитектура"]),
    ("building.historic", "История", "Историческое здание", ["история", "архитектура"]),
    ("tourism.sights.memorial", "История", "Памятник", ["памятник", "история"]),

    ("religion.place_of_worship", "Религия", "Храм", ["храм", "религия"]),

    ("leisure.park", "Природа", "Парк", ["парк", "природа"]),
    ("leisure.park.garden", "Природа", "Сад", ["сад", "природа"]),
    ("tourism.attraction.viewpoint", "Природа", "Смотровая площадка", ["вид", "панорама", "смотровая"]),
]

CUISINE_RU = {
    "russian": "русская", "georgian": "грузинская", "italian": "итальянская",
    "japanese": "японская", "sushi": "суши", "chinese": "китайская",
    "french": "французская", "european": "европейская", "asian": "азиатская",
    "uzbek": "узбекская", "armenian": "армянская", "caucasian": "кавказская",
    "indian": "индийская", "thai": "тайская", "vietnamese": "вьетнамская",
    "korean": "корейская", "mexican": "мексиканская", "american": "американская",
    "pizza": "пицца", "burger": "бургеры", "coffee_shop": "кофейня",
    "seafood": "морепродукты", "steak_house": "стейки", "vegetarian": "вегетарианская",
    "vegan": "веганская", "regional": "местная", "international": "интернациональная",
    "mediterranean": "средиземноморская", "bakery": "выпечка", "dessert": "десерты",
}
CUISINE_NOT_KITCHEN = {"пицца", "бургеры", "суши", "кофейня", "десерты", "выпечка", "стейки", "морепродукты"}

DAYS_RU = {"Mo": "Пн", "Tu": "Вт", "We": "Ср", "Th": "Чт", "Fr": "Пт", "Sa": "Сб", "Su": "Вс"}
MONTHS_RU = {
    "Jan": "янв", "Feb": "фев", "Mar": "мар", "Apr": "апр", "May": "мая", "Jun": "июн",
    "Jul": "июл", "Aug": "авг", "Sep": "сен", "Oct": "окт", "Nov": "ноя", "Dec": "дек",
}
OSM_TYPES = {"n": "node", "w": "way", "r": "relation",
             "node": "node", "way": "way", "relation": "relation"}


def osm_hours_to_ru(value):
    if not value:
        return None
    value = value.strip()
    if value == "24/7":
        return "Круглосуточно"

    text = value
    for en, ru in DAYS_RU.items():
        text = re.sub(rf"\b{en}\b", ru, text)
    for en, ru in MONTHS_RU.items():
        text = re.sub(rf"\b{en}\b", ru, text)
    text = re.sub(r"\bPH\b", "праздники", text)
    text = re.sub(r"\b(off|closed)\b", "выходной", text)
    text = text.replace("sunrise", "рассвет").replace("sunset", "закат")
    text = text.replace("24/7", "круглосуточно")

    return "\n".join(part.strip() for part in text.split(";") if part.strip())


class GeoapifyParser:

    def __init__(self, images_dir="data/geoapify_images", per_category=2, area="center",
                 require_details=True):
        self.api_key = os.getenv("GEOAPIFY_KEY")
        self.images_dir = images_dir
        self.per_category = per_category
        self.area = area
        self.require_details = require_details
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.requests_made = 0
        self._wiki_cache = {}
        self._wiki_last = {}
        self.web_session = requests.Session()
        self.web_session.headers.update({"User-Agent": BROWSER_UA})
        os.makedirs(images_dir, exist_ok=True)


    def hide_key(self, text):
        return str(text).replace(self.api_key, "***") if self.api_key else str(text)

    def geoapify_get(self, url, params, retries=3):
        params = {**params, "apiKey": self.api_key}

        for attempt in range(1, retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=60)
            except Exception as e:
                print(f"geoapify: сетевая ошибка, попытка {attempt}/{retries}: "
                      f"{type(e).__name__}: {self.hide_key(e)[:300]}")
                time.sleep(2 * attempt)
                continue

            if response.status_code == 200:
                self.requests_made += 1
                time.sleep(0.25)
                return response.json()
            if response.status_code == 401:
                raise RuntimeError("Geoapify отклонил ключ (401) — проверьте GEOAPIFY_KEY в .env")
            if response.status_code == 429:
                print("geoapify: превышен лимит запросов (429), жду 10 с")
                time.sleep(10)
                continue
            print(f"geoapify: ответ {response.status_code}: {self.hide_key(response.text)[:300]}")
            return None

        return None

    def get_json(self, url, params=None, retries=3):
        cache_key = (url, tuple(sorted((params or {}).items())))
        if cache_key in self._wiki_cache:
            return self._wiki_cache[cache_key]

        host = url.split("/")[2]
        for attempt in range(1, retries + 1):
            wait = WIKI_MIN_INTERVAL - (time.time() - self._wiki_last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self._wiki_last[host] = time.time()
            try:
                response = self.session.get(url, params=params, timeout=30)
            except Exception as e:
                print(f"{host}: сетевая ошибка, попытка {attempt}/{retries} ({type(e).__name__})")
                time.sleep(2 * attempt)
                continue

            if response.status_code == 200:
                data = response.json()
                self._wiki_cache[cache_key] = data
                return data
            if response.status_code == 404:
                self._wiki_cache[cache_key] = None
                return None
            print(f"{host}: ответ {response.status_code}, попытка {attempt}/{retries}")
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "")
                time.sleep(int(retry_after) if retry_after.isdigit() else 20 * attempt)
            else:
                time.sleep(2 * attempt)
        return None


    @staticmethod
    def split_rect(rect, n):
        lon1, lat1, lon2, lat2 = map(float, rect.split(","))
        dlon, dlat = (lon2 - lon1) / n, (lat2 - lat1) / n
        return [
            f"{lon1 + i * dlon:.5f},{lat1 + j * dlat:.5f},"
            f"{lon1 + (i + 1) * dlon:.5f},{lat1 + (j + 1) * dlat:.5f}"
            for i in range(n) for j in range(n)
        ]

    def cached_places(self, rect, categories):
        params = {
            "categories": categories,
            "filter": f"rect:{rect}",
            "conditions": "named",
            "limit": PAGE_LIMIT,
            "lang": "ru",
        }
        os.makedirs(CACHE_DIR, exist_ok=True)
        key = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()
        cache_file = os.path.join(CACHE_DIR, f"{key}.json")
        if os.path.exists(cache_file) and time.time() - os.path.getmtime(cache_file) < CACHE_TTL_SECONDS:
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)

        data = self.geoapify_get(PLACES_URL, params, retries=2)
        if data is None:
            return None
        features = data.get("features") or []
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(features, f, ensure_ascii=False)
        return features

    def fetch_rect(self, rect, categories, depth=0):
        features = self.cached_places(rect, categories)

        too_big = features is None or len(features) >= PAGE_LIMIT
        if too_big and depth < MAX_SPLIT_DEPTH:
            result = list(features or [])
            for sub in self.split_rect(rect, 2):
                result.extend(self.fetch_rect(sub, categories, depth + 1))
            return result

        if features is None:
            print(f"geoapify: квадрат {rect} не загрузился, пропускаю")
            return []
        return features

    def fetch_all(self):
        area_rect, grid = AREAS[self.area]
        categories = ",".join(code for code, *_ in PLACE_TYPES)
        cells = self.split_rect(area_rect, grid)

        found = {}
        for i, cell in enumerate(cells, 1):
            for feature in self.fetch_rect(cell, categories):
                props = feature.get("properties") or {}
                if props.get("place_id") and self.in_spb(feature):
                    found[props["place_id"]] = feature
            print(f"geoapify: квадрат {i}/{len(cells)}, всего мест: {len(found)}")
        return list(found.values())

    @staticmethod
    def match_type(feature):
        cats = (feature.get("properties") or {}).get("categories") or []
        best = None
        for place_type in PLACE_TYPES:
            code = place_type[0]
            if code in cats and (best is None or len(code) > len(best[0])):
                best = place_type
        return best

    @staticmethod
    def in_spb(feature):
        props = feature.get("properties") or {}
        return SPB_NAME in (props.get("state"), props.get("city"), props.get("county"))


    @staticmethod
    def to_element(feature):
        props = feature.get("properties") or {}
        raw = dict(((props.get("datasource") or {}).get("raw")) or {})

        wiki = props.get("wiki_and_media") or {}
        contact = props.get("contact") or {}
        for key, value in (
            ("name", props.get("name")),
            ("opening_hours", props.get("opening_hours")),
            ("website", props.get("website")),
            ("phone", contact.get("phone")),
            ("wikidata", wiki.get("wikidata")),
            ("wikipedia", wiki.get("wikipedia")),
            ("image", wiki.get("image")),
        ):
            if value and not raw.get(key):
                raw[key] = value

        osm_type = OSM_TYPES.get(str(raw.get("osm_type") or "").lower())
        osm_id = raw.get("osm_id")
        if osm_id is not None:
            osm_id = abs(int(osm_id))

        return {
            "type": osm_type,
            "id": osm_id,
            "place_id": props.get("place_id"),
            "lat": props.get("lat"),
            "lon": props.get("lon"),
            "distance": props.get("distance") or 0,
            "tags": raw,
            "props": props,
        }


    @staticmethod
    def score(tags):
        s = 0
        s += 3 if tags.get("wikidata") else 0
        s += 2 if tags.get("wikipedia") else 0
        s += 2 if tags.get("image") or tags.get("wikimedia_commons") else 0
        s += 2 if tags.get("opening_hours") else 0
        s += 1 if tags.get("website") or tags.get("contact:website") else 0
        s += 1 if tags.get("phone") or tags.get("contact:phone") else 0
        s += 1 if tags.get("description") or tags.get("description:ru") else 0
        s -= 3 if tags.get("brand") or tags.get("brand:wikidata") else 0
        return s


    def wikidata_info(self, qid):
        if not qid or not re.fullmatch(r"Q\d+", str(qid)):
            return None, None
        data = self.get_json(WIKIDATA_URL.format(qid=qid))
        if not data:
            return None, None
        entity = (data.get("entities") or {}).get(qid) or {}

        wiki_title = ((entity.get("sitelinks") or {}).get("ruwiki") or {}).get("title")

        image = None
        for claim in (entity.get("claims") or {}).get("P18", []):
            image = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if image:
                break
        return wiki_title, image

    def wikipedia_summary(self, title):
        if not title:
            return None
        data = self.get_json(WIKIPEDIA_SUMMARY_URL.format(title=quote(title.replace(" ", "_"))))
        if not data or data.get("type") == "disambiguation":
            return None
        return clean_text(data.get("extract"))

    def commons_thumb_url(self, filename, width=1024):
        filename = re.sub(r"^(File|Файл):", "", filename or "").strip()
        if not filename:
            return None
        data = self.get_json(COMMONS_API_URL, params={
            "action": "query",
            "titles": f"File:{filename}",
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": width,
            "format": "json",
        })
        if not data:
            return None
        for page in (data.get("query") or {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            return info.get("thumburl") or info.get("url")
        return None

    @staticmethod
    def build_address(props, name):
        street = props.get("street")
        house = props.get("housenumber")
        if street and house:
            return f"{street}, {house}"
        if street:
            return street

        if props.get("lat") is not None and props.get("lon") is not None:
            address = reverse_geocode(props["lat"], props["lon"])
            if address:
                return address

        parts = [p.strip() for p in (props.get("formatted") or "").split(",")]
        skip = {"россия", "санкт-петербург", (name or "").lower()}
        parts = [p for p in parts if p and p.lower() not in skip and not re.fullmatch(r"\d{6}", p)]
        if parts:
            return ", ".join(parts[:3])
        return props.get("suburb") or props.get("district")

    @staticmethod
    def build_description(tags, type_name):
        own = clean_text(tags.get("description:ru") or tags.get("description") or "")
        if own and len(own) >= 40 and re.search(r"[а-яё]", own, re.IGNORECASE):
            return own

        parts = [f"{type_name}."]
        cuisines = [CUISINE_RU[c.strip()] for c in (tags.get("cuisine") or "").split(";")
                    if c.strip() in CUISINE_RU]
        if cuisines:
            parts.append(f"Кухня: {', '.join(cuisines)}.")

        features = []
        if tags.get("outdoor_seating") == "yes":
            features.append("летняя веранда")
        if tags.get("internet_access") in ("wlan", "yes"):
            features.append("Wi-Fi")
        if features:
            parts.append(f"Есть {', '.join(features)}.")
        if tags.get("wheelchair") == "yes":
            parts.append("Доступно для колясок.")
        if tags.get("fee") == "no":
            parts.append("Вход бесплатный.")

        return " ".join(parts) if len(parts) > 1 else None

    @staticmethod
    def build_tags(tags, base_tags):
        result = list(base_tags)
        for c in (tags.get("cuisine") or "").split(";"):
            c = CUISINE_RU.get(c.strip())
            if c and c not in CUISINE_NOT_KITCHEN:
                result.append(f"{c} кухня")
            elif c:
                result.append(c)
        if tags.get("fee") == "no":
            result.append("бесплатно")
        if tags.get("outdoor_seating") == "yes":
            result.append("веранда")
        if tags.get("kids_area") == "yes" or tags.get("playground") == "yes":
            result.append("детям")
        return list(dict.fromkeys(result))


    def commons_category_file(self, category):
        data = self.get_json(COMMONS_API_URL, params={
            "action": "query", "list": "categorymembers", "cmtitle": category,
            "cmtype": "file", "cmlimit": 20, "format": "json",
        })
        for member in ((data or {}).get("query") or {}).get("categorymembers", []):
            title = member.get("title", "")
            if title.lower().endswith(IMAGE_EXTENSIONS):
                return title
        return None

    def wikipedia_image_url(self, title, width=1024):
        if not title:
            return None
        data = self.get_json(WIKIPEDIA_API_URL, params={
            "action": "query", "prop": "pageimages", "titles": title,
            "piprop": "thumbnail", "pithumbsize": width, "redirects": 1, "format": "json",
        })
        for page in ((data or {}).get("query") or {}).get("pages", {}).values():
            source = (page.get("thumbnail") or {}).get("source")
            if source:
                return source
        return None

    def website_image_url(self, website):
        if not website:
            return None
        if not website.startswith("http"):
            website = "https://" + website
        try:
            response = requests.get(website, headers={"User-Agent": BROWSER_UA}, timeout=10)
            if response.status_code != 200 or "html" not in response.headers.get("Content-Type", ""):
                return None
        except Exception:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        for selector in ('meta[property="og:image"]', 'meta[name="og:image"]',
                         'meta[name="twitter:image"]', 'meta[property="twitter:image"]'):
            tag = soup.select_one(selector)
            url = (tag.get("content") or "").strip() if tag else ""
            if url and self.looks_like_photo(url):
                return urljoin(response.url, url)

        for img in soup.find_all("img"):
            url = img.get("data-original") or img.get("data-src") or img.get("src") or ""
            if not url and img.get("srcset"):
                url = img["srcset"].split(",")[0].split()[0]
            url = url.strip()
            if not url or url.startswith("data:"):
                continue
            width = re.sub(r"\D", "", str(img.get("width") or ""))
            if width and int(width) < 300:
                continue
            if self.looks_like_photo(url) and url.lower().split("?")[0].endswith(IMAGE_EXTENSIONS):
                return urljoin(response.url, url)
        return None

    @staticmethod
    def looks_like_photo(url):
        if url.startswith("undefined") or "undefined/" in url:
            return False
        if re.search(r"mc\.yandex|counter|top-fwz|pixel|analytics", url, re.IGNORECASE):
            return False
        return not re.search(r"logo|favicon|icon|sprite|\.svg|\.gif", url, re.IGNORECASE)

    def nearby_commons_file(self, lat, lon, name, radius=100):
        data = self.get_json(COMMONS_API_URL, params={
            "action": "query", "list": "geosearch", "gscoord": f"{lat}|{lon}",
            "gsradius": radius, "gsnamespace": 6, "gslimit": 20, "format": "json",
        })
        files = [f["title"] for f in ((data or {}).get("query") or {}).get("geosearch", [])
                 if f.get("title", "").lower().endswith(IMAGE_EXTENSIONS)]
        if not files:
            return None
        words = [w for w in re.findall(r"[а-яёa-z]{4,}", (name or "").lower())]
        for title in files:
            if any(w[:6] in title.lower() for w in words):
                return title
        return files[0]

    def save_photo(self, image_url, name):
        if not image_url:
            return None
        is_wikimedia = "wikimedia.org" in image_url or "wikipedia.org" in image_url
        session = self.session if is_wikimedia else self.web_session
        saved = download_image(image_url, name, self.images_dir, session=session)
        if not saved:
            return None
        return f"{os.path.basename(self.images_dir)}/{os.path.basename(saved)}"

    def download_photo(self, tags, name, wd_image, wiki_title, category, lat, lon):
        commons_tag = tags.get("wikimedia_commons") or ""
        image_tag = tags.get("image") or ""

        def from_commons_file(file_name):
            url = self.commons_thumb_url(file_name) if file_name else None
            return self.save_photo(url, name) if url else None

        sources = [
            ("wikidata", lambda: from_commons_file(wd_image)),
            ("commons", lambda: from_commons_file(
                self.commons_category_file(commons_tag) if commons_tag.startswith("Category:")
                else commons_tag)),
            ("osm_image", lambda: (
                from_commons_file(image_tag.rsplit("/", 1)[-1]) if "wikimedia.org" in image_tag
                else self.save_photo(image_tag, name) if image_tag.lower().startswith("http")
                and image_tag.lower().split("?")[0].endswith(IMAGE_EXTENSIONS)
                else None)),
            ("wikipedia", lambda: self.save_photo(self.wikipedia_image_url(wiki_title), name)
                if wiki_title else None),
            ("website", lambda: self.save_photo(
                self.website_image_url(tags.get("website") or tags.get("contact:website")), name)
                if (tags.get("website") or tags.get("contact:website")) else None),
            ("commons_nearby", lambda: from_commons_file(self.nearby_commons_file(lat, lon, name))
                if category in NEARBY_PHOTO_CATEGORIES else None),
        ]

        for source, fetch in sources:
            try:
                path = fetch()
            except Exception as e:
                print(f"фото «{name}» ({source}): ошибка {type(e).__name__}")
                path = None
            if path:
                return path, source
        return None, None

    def format_place(self, element, category, type_name, base_tags):
        tags, props = element["tags"], element["props"]
        lat, lon = element["lat"], element["lon"]
        if lat is None or lon is None:
            return None

        name = tags.get("name:ru") or tags.get("name")
        name = str(name).strip() if name is not None else None
        address = self.build_address(props, name)
        if not name or not address:
            return None

        wiki_title, wd_image = self.wikidata_info(tags.get("wikidata"))
        if not wiki_title and str(tags.get("wikipedia") or "").startswith("ru:"):
            wiki_title = tags["wikipedia"][3:]

        description = self.wikipedia_summary(wiki_title) or self.build_description(tags, type_name)
        image_filename, image_source = self.download_photo(
            tags, name, wd_image, wiki_title, category, lat, lon)

        if element["type"] and element["id"]:
            place_id = f"osm_{element['type']}_{element['id']}"
            url = f"https://www.openstreetmap.org/{element['type']}/{element['id']}"
        else:
            place_id = f"geoapify_{element['place_id']}"
            url = None

        return {
            "id": place_id,
            "name": clean_text(name),
            "address": address,
            "coords": {"lat": lat, "lon": lon},
            "metro": None,
            "description": description,
            "tags": self.build_tags(tags, base_tags),
            "category": category,
            "work_time": osm_hours_to_ru(tags.get("opening_hours")),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "source": "geoapify",
            "image_filename": image_filename,
            "image_source": image_source,
            "url": url,
        }

    @staticmethod
    def is_excluded(element):
        tags = element["tags"]
        text = f"{tags.get('name', '')} {tags.get('description', '')}".lower()
        if tags.get("amenity") in ("stripclub", "brothel"):
            return True
        return any(word in text for word in ADULT_KEYWORDS)

    def has_details(self, element, category):
        if self.is_excluded(element):
            return False
        if not self.require_details or category not in ("Еда и напитки", "Развлечения"):
            return True
        tags = element["tags"]
        return bool(tags.get("opening_hours") or tags.get("website") or tags.get("contact:website"))

    def parse(self):
        if not self.api_key:
            print("geoapify: нет GEOAPIFY_KEY в .env — пропускаю")
            return []

        try:
            features = self.fetch_all()
        except RuntimeError as e:
            print(f"geoapify: {e}")
            return []
        print(f"geoapify: запросов к API: {self.requests_made}, мест в области: {len(features)}")

        by_type = {}
        for feature in features:
            place_type = self.match_type(feature)
            if place_type:
                by_type.setdefault(place_type[0], []).append(self.to_element(feature))

        results = []
        for place_type in PLACE_TYPES:
            code, category, type_name, base_tags = place_type
            elements = [e for e in by_type.get(code, []) if self.has_details(e, category)]
            for e in elements:
                e["distance"] = distance(e["lat"], e["lon"], SPB_CENTER[1], SPB_CENTER[0]) or 0
            elements.sort(key=lambda e: (-self.score(e["tags"]), e["distance"]))

            taken = 0
            taken_names = set()
            for element in elements:
                if self.per_category is not None and taken >= self.per_category:
                    break
                name_key = str(element["tags"].get("name") or "").strip().lower()
                if name_key in taken_names:
                    continue
                try:
                    place = self.format_place(element, category, type_name, base_tags)
                except Exception as e:
                    print(f"geoapify: ошибка «{element['tags'].get('name')}»: {e}")
                    continue
                if place:
                    results.append(place)
                    taken_names.add(name_key)
                    taken += 1

            print(f"geoapify: {type_name}: найдено {len(by_type.get(code, []))}, "
                  f"с данными {len(elements)}, взято {taken}")

        return results


if __name__ == "__main__":
    parser = GeoapifyParser()
    results = parser.parse()
    save_to_json(results, "data/geoapify_places.json")
