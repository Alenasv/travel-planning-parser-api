import psycopg2
from psycopg2.extras import execute_values, Json


DB_CONFIG = {
    "dbname": "test01",
    "user": "postgres",
    "password": "dctvghbdtn200HFP!",
    "host": "45.150.11.208",
    "port": 5432
}

def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def insert_places(data):
    conn = get_conn()
    cur = conn.cursor()

    query = """
    INSERT INTO places (
        id, name, category, address,
        description, work_time,
        tags, coords, image_filename,
        source, url
    ) VALUES %s
    ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    category = EXCLUDED.category,
    address = EXCLUDED.address,
    description = EXCLUDED.description,
    work_time = EXCLUDED.work_time,
    tags = EXCLUDED.tags,
    coords = EXCLUDED.coords,
    image_filename = EXCLUDED.image_filename,
    source = EXCLUDED.source,
    url = EXCLUDED.url;
    """

    values = []

    for item in data:
        values.append((
            item.get("id"),
            item.get("name"),
            item.get("category"),
            item.get("address"),
            item.get("description"),
            item.get("work_time"),
            item.get("tags") or [],
            Json(item.get("coords") or {}),
            item.get("image_filename"),
            item.get("source"),
            item.get("url"),
        ))

    execute_values(cur, query, values)

    conn.commit()
    cur.close()
    conn.close()