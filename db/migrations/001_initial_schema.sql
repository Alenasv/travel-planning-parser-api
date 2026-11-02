CREATE TABLE IF NOT EXISTS public.places (
    id text PRIMARY KEY,
    name text NOT NULL,
    category text,
    address text,
    metro text,
    description text,
    work_time text,
    tags text[] NOT NULL DEFAULT '{}',
    coords jsonb NOT NULL DEFAULT '{}',
    image_filename text,
    source text,
    url text,
    opening_hours jsonb NOT NULL DEFAULT '{}',
    phone text,
    website text,
    image_source text,
    metro_distance_km double precision
);

CREATE TABLE IF NOT EXISTS public.metro_stations (
    name text PRIMARY KEY,
    lat double precision NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon double precision NOT NULL CHECK (lon BETWEEN -180 AND 180)
);

SELECT id, name, category, address, metro, description, work_time, tags,
       coords, image_filename, source, url, opening_hours, phone, website,
       image_source, metro_distance_km
FROM public.places LIMIT 0;

SELECT name, lat, lon FROM public.metro_stations LIMIT 0;
