import os
import logging
import requests
import time
from app.db.database import get_all_metro_stations
from math import radians, sin, cos, sqrt, atan2

from app.config import (
    GEOAPIFY_KEY,
    GEOAPIFY_GEOCODE_URL,
    GEOAPIFY_REVERSE_URL,
    GEOAPIFY_SPB_FILTER,
    GEOAPIFY_GEOCODE_TIMEOUT,
    NOMINATIM_SEARCH_URL,
    NOMINATIM_REVERSE_URL,
    NOMINATIM_USER_AGENT,
    NOMINATIM_TIMEOUT,
    NOMINATIM_MIN_INTERVAL,
)
logger = logging.getLogger(__name__)
GEOCODE_CACHE = {}
_last_geocode_at = 0.0

def _nominatim_wait():
    global _last_geocode_at
    wait = NOMINATIM_MIN_INTERVAL - (time.time() - _last_geocode_at)
    if wait > 0:
        time.sleep(wait)
    _last_geocode_at = time.time()



def _geoapify_request(url, params):
    key = GEOAPIFY_KEY
    if not key:
        return None
    try:
        response = requests.get(
            url,
            params={**params, "apiKey": key},
            timeout=GEOAPIFY_GEOCODE_TIMEOUT
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        logger.exception("Geoapify geocode: сетевая ошибка")
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
            NOMINATIM_REVERSE_URL,
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "zoom": 18,
                "accept-language": "ru"
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=NOMINATIM_TIMEOUT
        )
        data = response.json()
    except Exception:
        logger.exception("Reverse geocode error")
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

    url = NOMINATIM_SEARCH_URL

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
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=NOMINATIM_TIMEOUT
        )

        data = response.json()

        if data:
            result = {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"])
            }

            GEOCODE_CACHE[address] = result
            return result

    except Exception:
        logger.exception("Geocode error")

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



_metro_stations_cache = None

def nearest_metro(lat, lon):
    global _metro_stations_cache

    if _metro_stations_cache is None:
        _metro_stations_cache = get_all_metro_stations()

    if not _metro_stations_cache:
        return None, None

    best = None
    best_dist = float("inf")

    for station in _metro_stations_cache:
        d = distance(lat, lon, station["lat"], station["lon"])

        if d is not None and d < best_dist:
            best_dist = d
            best = station

    if best is None:
        return None, None

    return best["name"], round(best_dist, 2)