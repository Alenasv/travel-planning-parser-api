import os
import requests
import time
from math import radians, sin, cos, sqrt, atan2
from dotenv import load_dotenv

load_dotenv()

METRO_STATIONS = [
    {"name": "Девяткино", "lat": 60.0501, "lon": 30.4422},
    {"name": "Гражданский проспект", "lat": 60.0356, "lon": 30.4167},
    {"name": "Академическая", "lat": 60.0132, "lon": 30.3961},
    {"name": "Политехническая", "lat": 60.0083, "lon": 30.3703},
    {"name": "Площадь Мужества", "lat": 59.9978, "lon": 30.3600},
    {"name": "Лесная", "lat": 59.9850, "lon": 30.3447},
    {"name": "Выборгская", "lat": 59.9713, "lon": 30.3475},
    {"name": "Площадь Ленина", "lat": 59.9556, "lon": 30.3572},
    {"name": "Чернышевская", "lat": 59.9444, "lon": 30.3597},
    {"name": "Площадь Восстания", "lat": 59.9311, "lon": 30.3608},  
    {"name": "Владимирская", "lat": 59.9275, "lon": 30.3475},       
    {"name": "Пушкинская", "lat": 59.9206, "lon": 30.3294},         
    {"name": "Технологический институт", "lat": 59.9164, "lon": 30.3186}, 
    {"name": "Балтийская", "lat": 59.9075, "lon": 30.2992},
    {"name": "Нарвская", "lat": 59.9006, "lon": 30.2747},
    {"name": "Кировский завод", "lat": 59.8797, "lon": 30.2611},
    {"name": "Автово", "lat": 59.8675, "lon": 30.2583},
    {"name": "Ленинский проспект", "lat": 59.8531, "lon": 30.2689},
    {"name": "Проспект Ветеранов", "lat": 59.8425, "lon": 30.2539},
    
    {"name": "Парнас", "lat": 60.0692, "lon": 30.3336},
    {"name": "Проспект Просвещения", "lat": 60.0519, "lon": 30.3325},
    {"name": "Озерки", "lat": 60.0369, "lon": 30.3197},
    {"name": "Удельная", "lat": 60.0167, "lon": 30.3156},
    {"name": "Пионерская", "lat": 60.0028, "lon": 30.2964},
    {"name": "Чёрная речка", "lat": 59.9861, "lon": 30.3008},
    {"name": "Петроградская", "lat": 59.9662, "lon": 30.3112},
    {"name": "Горьковская", "lat": 59.9586, "lon": 30.3180},
    {"name": "Невский проспект", "lat": 59.9350, "lon": 30.3247},    
    {"name": "Сенная площадь", "lat": 59.9275, "lon": 30.3206},      
    {"name": "Технологический институт", "lat": 59.9167, "lon": 30.3184},
    {"name": "Фрунзенская", "lat": 59.9072, "lon": 30.3181},
    {"name": "Московские ворота", "lat": 59.8928, "lon": 30.3189},
    {"name": "Электросила", "lat": 59.8781, "lon": 30.3181},
    {"name": "Парк Победы", "lat": 59.8653, "lon": 30.3222},
    {"name": "Московская", "lat": 59.8525, "lon": 30.3228},
    {"name": "Звёздная", "lat": 59.8331, "lon": 30.3494},
    {"name": "Купчино", "lat": 59.8233, "lon": 30.3756},
    
    {"name": "Беговая", "lat": 59.9883, "lon": 30.2036},
    {"name": "Зенит", "lat": 59.9708, "lon": 30.2478},
    {"name": "Приморская", "lat": 59.9483, "lon": 30.2328},
    {"name": "Василеостровская", "lat": 59.9422, "lon": 30.2781},
    {"name": "Гостиный двор", "lat": 59.9341, "lon": 30.3300},
    {"name": "Маяковская", "lat": 59.9317, "lon": 30.3547},         
    {"name": "Площадь Александра Невского-1", "lat": 59.9244, "lon": 30.3853},
    {"name": "Елизаровская", "lat": 59.8967, "lon": 30.4231},
    {"name": "Ломоносовская", "lat": 59.8775, "lon": 30.4414},
    {"name": "Пролетарская", "lat": 59.8653, "lon": 30.4700},
    {"name": "Обухово", "lat": 59.8486, "lon": 30.4583},
    {"name": "Рыбацкое", "lat": 59.8300, "lon": 30.4986},
    
    {"name": "Спасская", "lat": 59.9269, "lon": 30.3194},           
    {"name": "Достоевская", "lat": 59.9281, "lon": 30.3458},       
    {"name": "Лиговский проспект", "lat": 59.9206, "lon": 30.3553},
    {"name": "Площадь Александра Невского-2", "lat": 59.9250, "lon": 30.3831},
    {"name": "Новочеркасская", "lat": 59.9314, "lon": 30.4114},
    {"name": "Ладожская", "lat": 59.9328, "lon": 30.4392},
    {"name": "Проспект Большевиков", "lat": 59.9236, "lon": 30.4631},
    {"name": "Улица Дыбенко", "lat": 59.9092, "lon": 30.4831},
    
    {"name": "Комендантский проспект", "lat": 60.0092, "lon": 30.2639},
    {"name": "Старая Деревня", "lat": 59.9894, "lon": 30.2553},
    {"name": "Крестовский остров", "lat": 59.9717, "lon": 30.2581},
    {"name": "Чкаловская", "lat": 59.9608, "lon": 30.2947},
    {"name": "Спортивная", "lat": 59.9514, "lon": 30.2872},
    {"name": "Адмиралтейская", "lat": 59.9356, "lon": 30.3139},
    {"name": "Садовая", "lat": 59.9267, "lon": 30.3183},           
    {"name": "Звенигородская", "lat": 59.9203, "lon": 30.3350},     
    {"name": "Обводный канал", "lat": 59.9128, "lon": 30.3436},
    {"name": "Волковская", "lat": 59.8956, "lon": 30.3583},
    {"name": "Бухарестская", "lat": 59.8853, "lon": 30.3806},
    {"name": "Международная", "lat": 59.8722, "lon": 30.3914},
    {"name": "Проспект Славы", "lat": 59.8583, "lon": 30.4008},
    {"name": "Дунайская", "lat": 59.8408, "lon": 30.4139},
    {"name": "Шушары", "lat": 59.8203, "lon": 30.4244},
] 

GEOCODE_CACHE = {}
NOMINATIM_MIN_INTERVAL = 1.1
_last_geocode_at = 0.0
def _nominatim_wait():
    global _last_geocode_at
    wait = NOMINATIM_MIN_INTERVAL - (time.time() - _last_geocode_at)
    if wait > 0:
        time.sleep(wait)
    _last_geocode_at = time.time()


GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_REVERSE_URL = "https://api.geoapify.com/v1/geocode/reverse"
GEOAPIFY_SPB_FILTER = "rect:29.42,59.63,30.76,60.25"


def _geoapify_request(url, params):
    key = os.getenv("GEOAPIFY_KEY")
    if not key:
        return None
    try:
        response = requests.get(url, params={**params, "apiKey": key}, timeout=20)
        if response.status_code == 200:
            return response.json()
        print(f"Geoapify geocode: ответ {response.status_code}")
    except Exception as e:
        print(f"Geoapify geocode: сетевая ошибка ({type(e).__name__})")
    return None


def _short_address(result):
    street = result.get("street")
    house = result.get("housenumber")
    if street and house:
        return f"{street}, {house}"
    return street


def reverse_geocode(lat, lon):
    data = _geoapify_request(GEOAPIFY_REVERSE_URL, {
        "lat": lat, "lon": lon, "lang": "ru", "format": "json", "limit": 1,
    })
    results = (data or {}).get("results") or []
    if results and _short_address(results[0]):
        return _short_address(results[0])
    return _nominatim_reverse(lat, lon)


def _nominatim_reverse(lat, lon):
    _nominatim_wait()
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "zoom": 18,
                "accept-language": "ru"
            },
            headers={"User-Agent": "places-recommender/1.0"},
            timeout=10
        )
        data = response.json()
    except Exception as e:
        print(f"Reverse geocode error: {e}")
        return None

    addr = data.get("address") or {}
    road = addr.get("road") or addr.get("pedestrian") or addr.get("footway")
    house = addr.get("house_number")
    if road and house:
        return f"{road}, {house}"
    if road:
        return road

    display = data.get("display_name")
    if display:
        return ", ".join(display.split(", ")[:3])
    return None


def geocode(address):
    if not address:
        return None
    key = address.strip().lower()
    if key in GEOCODE_CACHE:
        return GEOCODE_CACHE[key]

    data = _geoapify_request(GEOAPIFY_GEOCODE_URL, {
        "text": address, "lang": "ru", "format": "json", "limit": 1,
        "filter": GEOAPIFY_SPB_FILTER,
    })
    results = (data or {}).get("results") or []
    if results and results[0].get("lat") is not None:
        result = {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])}
        GEOCODE_CACHE[key] = result
        return result

    return _nominatim_geocode(address)


def _nominatim_geocode(address):
    if not address:
        return None

    address = address.strip().lower()

    if address in GEOCODE_CACHE:
        return GEOCODE_CACHE[address]

    url = "https://nominatim.openstreetmap.org/search"

    _nominatim_wait()

    try:
        response = requests.get(
            url,
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "countrycodes": "ru"
            },
            headers={"User-Agent": "places-recommender/1.0"},
            timeout=5
        )

        data = response.json()

        if data:
            result = {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"])
            }

            GEOCODE_CACHE[address] = result
            return result

    except Exception as e:
        print(f"Geocode error: {e}")

    GEOCODE_CACHE[address] = None
    return None


def distance(lat1, lon1, lat2, lon2):
    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
    except (TypeError, ValueError):
        return None

    R = 6371

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


def nearest_metro(lat, lon):
    best = None
    best_dist = float("inf")

    for m in METRO_STATIONS:
        d = distance(lat, lon, m["lat"], m["lon"])

        if d < best_dist:
            best_dist = d
            best = m

    if not best:
        return None, None

    return best["name"], round(best_dist, 2)
