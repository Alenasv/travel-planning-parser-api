import logging

import psycopg2
from psycopg2.extras import execute_values, Json, RealDictCursor

from app.config import (
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
    DB_HOST,
    DB_PORT,
)

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "dbname": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "host": DB_HOST,
    "port": DB_PORT,
}

def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def sync_places(data):


    if not data:
        raise ValueError(
            "Список мест пуст. Синхронизация отменена."
        )

    values = []
    seen_ids = set()

    for item in data:
        place_id = item.get("id")

        if not place_id:
            raise ValueError(
                f"У места отсутствует id: {item.get('name')}"
            )

        if place_id in seen_ids:
            raise ValueError(f"Повторяющийся id: {place_id}")

        seen_ids.add(place_id)

        coords = item.get("coords") or {}

        values.append((
            str(place_id),
            item.get("name"),
            item.get("category"),
            item.get("address"),
            item.get("metro"),
            item.get("description"),
            item.get("work_time"),
            item.get("tags") or [],
            Json(coords),
            item.get("image_filename"),
            item.get("source"),
            item.get("url"),
            Json(item.get("opening_hours") or {}),
            item.get("phone"),
            item.get("website"),
            item.get("image_source"),
            item.get("metro_distance_km"),
        ))

    conn = get_conn()

    try:
        with conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO public.places (
                        id, name, category, address, metro,
                        description, work_time, tags, coords,
                        image_filename, source, url,
                        opening_hours, phone, website,
                        image_source, metro_distance_km
                    )
                    VALUES %s
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        category = EXCLUDED.category,
                        address = EXCLUDED.address,
                        metro = EXCLUDED.metro,
                        description = EXCLUDED.description,
                        work_time = EXCLUDED.work_time,
                        tags = EXCLUDED.tags,
                        coords = EXCLUDED.coords,
                        image_filename = COALESCE(EXCLUDED.image_filename, places.image_filename),
                        source = EXCLUDED.source,
                        url = EXCLUDED.url,
                        opening_hours = EXCLUDED.opening_hours,
                        phone = EXCLUDED.phone,
                        website = EXCLUDED.website,
                        image_source = CASE
                            WHEN EXCLUDED.image_filename IS NOT NULL THEN EXCLUDED.image_source
                            ELSE places.image_source
                        END,
                        metro_distance_km = EXCLUDED.metro_distance_km
                    """,
                    values,
                )

        logger.info("Синхронизация завершена: обработано %s", len(values))


    except Exception:
        logger.exception("Ошибка синхронизации PostgreSQL")
        raise

    finally:
        conn.close()


def check_database():
    conn = get_conn()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database(), current_schema(), current_user"
            )
            info = cur.fetchone()

            cur.execute("SELECT COUNT(*) FROM public.places")
            count = cur.fetchone()[0]

        logger.info("Подключение к БД: %s", info)
        logger.info("Записей в public.places: %s", count)

    finally:
        conn.close()


def get_all_metro_stations():
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT name, lat, lon
                FROM public.metro_stations
                ORDER BY name
            """)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
def get_all_places():

    conn = get_conn()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    id,
                    name,
                    category,
                    address,
                    metro,
                    description,
                    work_time,
                    opening_hours,
                    tags,
                    coords,
                    image_filename,
                    source,
                    url,
                    phone,
                    website,
                    image_source,
                    metro_distance_km
                FROM public.places
                ORDER BY name
            """)

            places = [dict(row) for row in cur.fetchall()]

        for place in places:
            coords = place.get("coords") or {}
            place["lat"] = coords.get("lat")
            place["lon"] = coords.get("lon")

        logger.info("Загружено из PostgreSQL мест: %s", len(places))
        return places

    finally:
        conn.close()


